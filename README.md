# Conversational RAG Backend

A FastAPI backend for document ingestion and conversational retrieval-augmented
generation (RAG). It uses Qdrant for vector search, Redis for temporary
conversation memory, Postgres for metadata and confirmed bookings, and Groq
for LLM responses.

## Features

- Upload PDF and TXT documents.
- Choose fixed or recursive chunking.
- Generate embeddings and store document chunks in Qdrant.
- Ask multi-turn questions about indexed documents.
- Keep recent conversation history in Redis.
- Collect and confirm interview booking details, then store them in Postgres.
- Generate conversation IDs through the API.

## Requirements

- Docker Desktop with Docker Compose
- A Groq API key
- A Groq model enabled for your account

## Setup with Docker Compose

1. Clone this repository and open its directory.
2. Copy the example environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Edit `.env` and set `GROQ_API_KEY` and `GROQ_MODEL`.
4. Start the services and build the API image:

   ```powershell
   docker compose up --build -d
   ```

5. Apply the database migrations:

   ```powershell
   docker compose exec api alembic upgrade head
   ```

6. Open the interactive API documentation:

   [http://localhost:8000/docs](http://localhost:8000/docs)

The embedding model is downloaded when the API first starts, so the initial
startup may take longer.

> The repository's initial Alembic migration must create the `documents` and
> `bookings` tables before step 5 will work. Generate and commit a real migration
> before distributing this project.

## API endpoints

### Health

```http
GET /health
```

### Upload a document

```http
POST /documents
```

Send a `multipart/form-data` request with:

- `file`: a PDF or TXT file
- `strategy`: `fixed` or `recursive`
- `chunk_size`: optional chunk size
- `chunk_overlap`: optional chunk overlap

### Generate a conversation ID

GET /chat/conversation-id

### Chat

POST /chat

Send the generated conversation ID to continue the same conversation:


If a booking is confirmed, the name, email, date, and time are stored as a
booking record. The API does not check calendar availability or send calendar
invitations.

## Useful Docker commands

```powershell
docker compose ps
docker compose logs -f api
docker compose down
```

`docker compose down` stops the services but preserves their data volumes.