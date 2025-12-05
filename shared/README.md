# Shared Types and Schemas

This directory contains TypeScript type definitions and JSON schemas that are shared between the frontend and backend to ensure type safety and contract consistency.

## Structure

```
shared/
├── types/           # TypeScript type definitions
│   ├── company.ts   # Company, Contact, Product types
│   ├── job.ts       # Job and task types
│   ├── email.ts     # Campaign and EmailDraft types
│   ├── websocket.ts # WebSocket event types
│   └── index.ts     # Central export
└── schemas/         # JSON schemas for validation
    ├── company.schema.json
    ├── job.schema.json
    └── websocket.schema.json
```

## Usage

### Frontend (TypeScript/JavaScript)

```typescript
import { Company, Job, WebSocketMessage } from '../../../shared/types';

const company: Company = {
  id: '123',
  domain: 'example.com',
  // ...
};
```

### Backend (Python with Pydantic)

The backend should mirror these types in Pydantic schemas:

```python
# backend/app/schemas/company.py
from pydantic import BaseModel
from typing import List, Optional

class Contact(BaseModel):
    type: str  # email, phone, whatsapp, address
    value: str
    source: Optional[str] = None
    confidence: Optional[float] = None
```

## Principles

1. **Schema-First Design**: Define types here before implementing features
2. **Single Source of Truth**: Both frontend and backend reference these types
3. **Contract Preservation**: Breaking changes require version updates
4. **Type Safety**: Use TypeScript types on frontend, Pydantic on backend

## Validation

JSON schemas can be used for runtime validation:

```javascript
import Ajv from 'ajv';
import companySchema from '../schemas/company.schema.json';

const ajv = new Ajv();
const validate = ajv.compile(companySchema);
const valid = validate(companyData);
```

## Adding New Types

1. Create TypeScript definition in `types/`
2. Create corresponding JSON schema in `schemas/`
3. Export from `types/index.ts`
4. Update backend Pydantic schemas to match
5. Document in this README
