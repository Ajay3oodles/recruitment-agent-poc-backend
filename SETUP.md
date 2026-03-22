# Recruitment Agent POC Backend - Setup Guide

## ✅ Completed
- ✓ Python dependencies installed
- ✓ `.env` file created with default configuration

## 📋 Next Steps

### 1. Set up PostgreSQL Database with pgvector
This project requires PostgreSQL with the pgvector extension for vector search capabilities.

**Option A: Local PostgreSQL Installation**
```powershell
# Install PostgreSQL (if not already installed)
# Download from: https://www.postgresql.org/download/windows/

# Create database and enable pgvector
psql -U postgres

# In psql terminal:
CREATE DATABASE university_chatbot;
CREATE EXTENSION IF NOT EXISTS vector;
```

**Option B: Docker (Recommended)**
```powershell
# Pull PostgreSQL with pgvector
docker run --name postgres-pgvector `
  -e POSTGRES_PASSWORD=postgres `
  -e POSTGRES_DB=university_chatbot `
  -p 5432:5432 `
  -d ankane/pgvector

# Verify connection:
psql -h localhost -U postgres -d university_chatbot
```

### 2. Update Environment Variables
Edit `.env` file with your actual credentials:
- `DB_PASSWORD`: Your PostgreSQL password
- `WATSONX_API_KEY`: IBM Watson X API key
- `WATSONX_PROJECT_ID`: Watson X project ID
- `COSMOS_DB_CONNECTION_STRING`: (Optional) Azure Cosmos DB connection string

### 3. Run Django Migrations
```powershell
cd c:\Users\HP\Desktop\recruitment-agent-poc-backend
python manage.py migrate
```

### 4. Create Superuser (Optional - for Django Admin)
```powershell
python manage.py createsuperuser
```

### 5. Start Redis (for Celery)
```powershell
# Option A: Docker
docker run -d -p 6379:6379 redis:latest

# Option B: Windows (if Redis installed locally)
redis-server
```

### 6. Start Development Server
```powershell
# Terminal 1: Django server
python manage.py runserver

# Terminal 2: Celery worker (optional)
celery -A config worker --loglevel=info

# Terminal 3: Celery beat scheduler (optional)
celery -A config beat --loglevel=info
```

### 7. Access the Application
- API: http://localhost:8000
- Admin Panel: http://localhost:8000/admin
- API Documentation: http://localhost:8000/api/docs/

## 🔧 Configuration Details

### Key Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `DB_NAME` | PostgreSQL database name | `university_chatbot` |
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `WATSONX_API_KEY` | IBM Watson X authentication | Required |
| `CELERY_BROKER_URL` | Redis broker for async tasks | `redis://localhost:6379/0` |

### Project Structure
- `chatbot/` - Main Django app with models, views, serializers
- `config/` - Django settings and URL configuration
- `manage.py` - Django management script

### Database Models
The project uses PostgreSQL with pgvector for:
- Chat history storage
- Vector embeddings for semantic search
- Multi-tenant support

## 🚀 Troubleshooting

**Issue: "could not connect to server"**
- Ensure PostgreSQL is running: `psql -U postgres`
- Check connection settings in `.env`

**Issue: "psycopg2 error"**
- Reinstall: `pip install --force-reinstall psycopg2-binary`

**Issue: "No module named 'django'"**
- Reinstall dependencies: `pip install -r requirements.txt`

**Issue: "pgvector not found"**
- Enable pgvector in PostgreSQL: `CREATE EXTENSION IF NOT EXISTS vector;`

## 📚 Additional Resources
- [Django Documentation](https://docs.djangoproject.com/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [Celery Documentation](https://docs.celeryproject.org/)
- [IBM Watson X Documentation](https://www.ibm.com/products/watsonx)
