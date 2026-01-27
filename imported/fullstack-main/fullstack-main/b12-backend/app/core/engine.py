import joblib
import json
import pandas as pd

class B12ClinicalEngine:
    def __init__(self, model_dir="app/b12_clinical_engine_v1.0"):
        self.stage1 = joblib.load(f"{model_dir}/stage1_normal_vs_abnormal.pkl")
        self.stage2 = joblib.load(f"{model_dir}/stage2_borderline_vs_deficient.pkl")

        with open(f"{model_dir}/thresholds.json") as f:
            self.thresholds = json.load(f)

    def add_indices(self, row):
        row["Mentzer"] = row["MCV"] / row["RBC"]
        row["RDW_MCV"] = row["RDW"] / row["MCV"]
        row["Pancytopenia"] = int(
            (row["Hb"] < 12) and (row["WBC"] < 4) and (row["Platelets"] < 150)
        )
        return row

    def apply_rules(self, row):
        score = 0
        rules = []

        if row["MCV"] > 100:
            score += 1; rules.append("Macrocytosis")
        if row["RDW"] > 15:
            score += 1; rules.append("High RDW")
        if row["Mentzer"] > 13:
            score += 1; rules.append("Ineffective erythropoiesis")
        if row["Pancytopenia"] == 1:
            score += 2; rules.append("Pancytopenia")

        if row["MCV"] < 100 and row["Pancytopenia"] == 0:
            score -= 0.5; rules.append("No macrocytosis / no pancytopenia")
        if row["Hb"] > 11 and row["Platelets"] > 150:
            score -= 0.5; rules.append("Preserved cell counts")
        if row["MCV"] < 96 and row["RDW"] < 14 and row["Hb"] > 12:
            score -= 1; rules.append("Normal marrow pattern")

        return score, rules

    def predict(self, cbc_dict):
        # 1. Prepare raw input dataframe for Model
        # Map frontend keys to model keys if necessary.
        # Based on inspection, we need: Age, Sex, Hb, RBC, HCT, MCV, MCH, MCHC, RDW, WBC, Platelets, Neutrophils, Lymphocytes
        
        # Ensure 'Sex' is numeric if model expects it (usually converted)
        # However, CatBoost/XGBoost handles categories if specified.
        # Let's trust the input dictionary matches keys now that we fixed api.ts
        
        # The model likely expects 'Sex' as 0/1 or Category. 
        # Inspect output showed 'Sex', presumably string 'M'/'F' or encoded.
        # Assuming model handles 'M'/'F' or we need to encode.
        # Let's try passing as is first, but ensure all columns are present.

        df = pd.DataFrame([cbc_dict])
        
        # Reorder/Select columns strictly to avoid "extra column" errors or "missing column" errors
        expected_cols = [
            'Age', 'Sex', 'Hb', 'RBC', 'HCT', 'MCV', 'MCH', 'MCHC', 'RDW', 
            'WBC', 'Platelets', 'Neutrophils', 'Lymphocytes'
        ]
        
        # Ensure all columns exist (fill 0 or None if missing, though we fixed validation)
        for col in expected_cols:
            if col not in df.columns:
                df[col] = 0 # Fallback
                
        df = df[expected_cols] # Enforce order and selection

        # Fix: Map Sex to numeric if model expects it (CatBoost error confirmed this)
        # Assuming M=1, F=0 based on common practice. If model performs poorly, we swap.
        if df['Sex'].dtype == 'object':
            df['Sex'] = df['Sex'].map({'M': 1, 'F': 0, 'm': 1, 'f': 0})
            df['Sex'] = df['Sex'].fillna(0) # Separate fillna to Ensure processing
        
        p_abnormal = self.stage1.predict_proba(df)[0][1]
        p_def = self.stage2.predict_proba(df)[0][1] if p_abnormal > 0.3 else 0.05

        row = self.add_indices(cbc_dict)
        rule_score, rules = self.apply_rules(row)

        p_def_final = min(1, max(0, p_def + self.thresholds["rule_weight"] * rule_score))

        if p_def_final >= self.thresholds["deficient_threshold"]:
            cls = 3; label = "DEFICIENT"
        elif p_def_final >= self.thresholds["borderline_threshold"]:
            cls = 2; label = "BORDERLINE"
        else:
            cls = 1; label = "NORMAL"

        return {
            "riskClass": cls,
            "label": label,
            "probabilities": {
                "normal": round(1 - max(p_abnormal, p_def_final), 3),
                "borderline": round(max(0, p_abnormal - p_def_final), 3),
                "deficient": round(p_def_final, 3)
            },
            "rulesFired": rules,
            "modelVersion": "B12-Clinical-Engine-v1.0",
            "indices": {
                "mentzer": round(cbc_dict.get("MCV", 0) / cbc_dict.get("RBC", 1) if cbc_dict.get("RBC", 0) > 0 else 0, 2),
                "greenKing": round((pow(cbc_dict.get("MCV", 0), 2) * cbc_dict.get("RDW", 0)) / (100 * cbc_dict.get("Hb", 1)) if cbc_dict.get("Hb", 0) > 0 else 0, 2),
                "nlr": round((cbc_dict.get("Neutrophils") or 0) / (cbc_dict.get("Lymphocytes") or 1) if (cbc_dict.get("Lymphocytes") or 0) > 0 else 0, 2)
            }
        }
