// MongoDB Initialization Script
// This script runs when MongoDB container starts for the first time

db = db.getSiblingDB('clinomic');

// Create collections with validation schemas
db.createCollection('users', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['id', 'orgId', 'role'],
      properties: {
        id: { bsonType: 'string' },
        orgId: { bsonType: 'string' },
        name: { bsonType: 'string' },
        role: { enum: ['ADMIN', 'LAB', 'DOCTOR'] },
        passwordHash: { bsonType: 'string' },
        isActive: { bsonType: 'bool' },
        createdAt: { bsonType: 'string' },
        updatedAt: { bsonType: 'string' }
      }
    }
  }
});

db.createCollection('patients', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['id', 'orgId'],
      properties: {
        id: { bsonType: 'string' },
        orgId: { bsonType: 'string' },
        name: { bsonType: 'string' },
        age: { bsonType: 'int' },
        sex: { enum: ['M', 'F'] }
      }
    }
  }
});

db.createCollection('screenings');
db.createCollection('audit_logs_v2');
db.createCollection('audit_checkpoints');
db.createCollection('refresh_tokens');
db.createCollection('mfa_settings');
db.createCollection('user_devices');
db.createCollection('login_anomalies');
db.createCollection('labs');
db.createCollection('doctors');
db.createCollection('files');
db.createCollection('file_chunks');
db.createCollection('jobs');
db.createCollection('rate_limits');

// Create indexes
db.users.createIndex({ 'orgId': 1, 'id': 1 }, { unique: true });
db.patients.createIndex({ 'orgId': 1, 'id': 1 }, { unique: true });
db.screenings.createIndex({ 'orgId': 1, 'createdAt': -1 });
db.screenings.createIndex({ 'orgId': 1, 'doctorId': 1, 'createdAt': -1 });
db.audit_logs_v2.createIndex({ 'orgId': 1, 'sequence': 1 }, { unique: true });
db.audit_logs_v2.createIndex({ 'orgId': 1, 'timestamp': -1 });
db.audit_checkpoints.createIndex({ 'orgId': 1, 'upToSequence': 1 });
db.refresh_tokens.createIndex({ 'orgId': 1, 'userId': 1, 'tokenHash': 1 }, { unique: true });
db.refresh_tokens.createIndex({ 'expiresAt': 1 }, { expireAfterSeconds: 0 });
db.mfa_settings.createIndex({ 'userId': 1, 'orgId': 1 }, { unique: true });
db.user_devices.createIndex({ 'userId': 1, 'orgId': 1, 'fingerprintHash': 1 });
db.login_anomalies.createIndex({ 'userId': 1, 'timestamp': -1 });
db.login_anomalies.createIndex({ 'timestamp': 1 }, { expireAfterSeconds: 2592000 }); // 30 days TTL
db.labs.createIndex({ 'orgId': 1, 'id': 1 }, { unique: true });
db.doctors.createIndex({ 'orgId': 1, 'id': 1 }, { unique: true });
db.files.createIndex({ 'orgId': 1, 'id': 1 });
db.file_chunks.createIndex({ 'fileId': 1, 'n': 1 });
db.jobs.createIndex({ 'orgId': 1, 'createdAt': -1 });
db.rate_limits.createIndex({ 'timestamp': 1 }, { expireAfterSeconds: 3600 });

print('Clinomic database initialized successfully');
