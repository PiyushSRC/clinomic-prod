from typing import Generic, TypeVar, Type, Optional, List
from uuid import UUID
from sqlmodel import SQLModel, Session, select

ModelType = TypeVar("ModelType", bound=SQLModel)

class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], db: Session, org_id: UUID):
        """
        Base Repository that enforces tenant isolation.
        
        :param model: The SQLModel class
        :param db: Database session
        :param org_id: Org ID from validated Tenant Context (JWT)
        """
        self.model = model
        self.db = db
        self.org_id = org_id

    def get(self, id: UUID) -> Optional[ModelType]:
        statement = select(self.model).where(self.model.id == id).where(self.model.org_id == self.org_id)
        return self.db.exec(statement).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        statement = select(self.model).where(self.model.org_id == self.org_id).offset(skip).limit(limit)
        return self.db.exec(statement).all()

    def create(self, obj: ModelType) -> ModelType:
        # FORCE override org_id to ensure safety even if developer passed wrong one
        if hasattr(obj, "org_id"):
            obj.org_id = self.org_id
        
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, db_obj: ModelType, obj_in: ModelType) -> ModelType:
        # Verify ownership (redundant if fetched via get, but safe)
        if getattr(db_obj, "org_id", None) != self.org_id:
             raise ValueError("Security Violation: Accessing cross-tenant object during update")

        obj_data = obj_in.dict(exclude_unset=True)
        for key, value in obj_data.items():
            # Prevent changing org_id
            if key == "org_id":
                continue
            setattr(db_obj, key, value)
            
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def delete(self, id: UUID) -> ModelType:
        obj = self.get(id)
        if obj:
            self.db.delete(obj)
            self.db.commit()
        return obj
