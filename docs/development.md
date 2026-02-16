# Development Guide

## Overview

This guide covers development setup, code quality standards, testing, and contribution guidelines for Kids Story Agent.

## Development Setup

### Prerequisites

- **Python 3.11+**
- **PostgreSQL 15+** (local or Docker)
- **Redis 7+** (local or Docker)
- **Git**

### Local Setup

1. **Clone Repository**:
```bash
git clone <repository-url>
cd kids_story_agent
```

2. **Create Virtual Environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install Dependencies**:
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development dependencies
```

4. **Set Up Environment**:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Start Infrastructure**:
```bash
docker-compose up -d  # PostgreSQL and Redis
```

6. **Run Migrations**:
```bash
alembic upgrade head
```

7. **Start Services**:
```bash
# Terminal 1: API Server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Celery Worker
celery -A app.celery_app worker --loglevel=info

# Terminal 3: Streamlit UI (optional)
./run_streamlit.sh
```

## Code Quality Standards

### Linting

**Ruff** (fast Python linter):
```bash
ruff check .
ruff format .
```

**Configuration** (`pyproject.toml`):
```toml
[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W", "UP"]
ignore = ["E501"]  # Line length handled by formatter

[tool.ruff.format]
quote-style = "double"
```

### Type Checking

**mypy** (static type checker):
```bash
mypy app/
```

**Configuration** (`mypy.ini`):
```ini
[mypy]
python_version = 3.11
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = False
```

### Code Formatting

**Black** (code formatter):
```bash
black app/
```

**Configuration** (`pyproject.toml`):
```toml
[tool.black]
line-length = 100
target-version = ['py311']
```

### Pre-commit Hooks

Install pre-commit hooks:
```bash
pip install pre-commit
pre-commit install
```

**Configuration** (`.pre-commit-config.yaml`):
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.5.0
    hooks:
      - id: mypy
```

## Testing

### Unit Tests

**pytest** (testing framework):
```bash
pytest tests/unit/
```

**Test Structure**:
```
tests/
  unit/
    test_story_writer.py
    test_guardrails.py
    test_evaluation.py
  integration/
    test_api.py
    test_workflow.py
```

**Example Test**:
```python
import pytest
from app.agents.nodes.generation.story_writer import story_writer_node

def test_story_writer_generates_story():
    state = {
        "job_id": "test-123",
        "prompt": "A brave mouse",
        "age_group": "6-8",
    }
    result = story_writer_node(state)
    assert "story_text" in result
    assert len(result["story_text"]) > 0
```

### Integration Tests

**Test Full Workflow**:
```bash
pytest tests/integration/
```

**Example Integration Test**:
```python
import pytest
from app.agents.graph import run_story_generation

@pytest.mark.asyncio
async def test_full_story_generation():
    initial_state = {
        "job_id": "test-123",
        "prompt": "A brave mouse",
        "age_group": "6-8",
        "num_illustrations": 2,
        "generate_images": True,
        "generate_videos": False,
    }
    final_state = await run_story_generation(initial_state)
    assert final_state.get("story_text") is not None
```

### Test Coverage

**Coverage.py**:
```bash
pytest --cov=app --cov-report=html
```

**Target**: 80%+ code coverage

## Database Migrations

### Creating Migrations

**Alembic** (database migration tool):
```bash
# Create new migration
alembic revision --autogenerate -m "Add new column"

# Review generated migration
# Edit migration file if needed

# Apply migration
alembic upgrade head
```

### Migration Best Practices

1. **Review Auto-generated Migrations**: Always review before applying
2. **Test Migrations**: Test on development database first
3. **Backward Compatibility**: Ensure migrations are reversible
4. **Data Migrations**: Handle data transformations carefully

**Example Migration**:
```python
"""Add evaluation scores to story

Revision ID: abc123
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('stories', sa.Column('overall_score', sa.Float(), nullable=True))

def downgrade():
    op.drop_column('stories', 'overall_score')
```

## Project Structure

```
kids_story_agent/
  app/
    agents/
      graph.py              # LangGraph workflow
      state.py              # State definition
      nodes/
        generation/         # Generation nodes
        evaluation/         # Evaluation & guardrail nodes
        review/             # Review nodes
    api/
      stories.py           # Story API endpoints
      reviews.py           # Review API endpoints
      auth.py              # Authentication
    services/
      llm.py               # LLM service
      moderation.py        # Moderation service
      storage.py           # Storage service
    models/
      story.py             # Story models
      evaluation.py        # Evaluation models
      guardrail.py         # Guardrail models
    schemas/
      story.py             # Story schemas
      review.py            # Review schemas
    tasks/
      story_tasks.py       # Celery tasks
    config.py              # Configuration
    main.py                # FastAPI app
  tests/
    unit/
    integration/
  docs/
    architecture.md
    guardrails.md
    evaluation.md
    ...
  alembic/
    versions/              # Migration files
  requirements.txt
  requirements-dev.txt
  pyproject.toml
  README.md
```

## Development Workflow

### Branch Strategy

- **main**: Production-ready code
- **develop**: Development branch
- **feature/**: Feature branches
- **bugfix/**: Bug fix branches

### Pull Request Process

1. **Create Feature Branch**:
```bash
git checkout -b feature/new-feature
```

2. **Make Changes**:
- Write code
- Add tests
- Update documentation

3. **Run Quality Checks**:
```bash
ruff check .
mypy app/
pytest tests/
```

4. **Commit Changes**:
```bash
git add .
git commit -m "Add new feature"
```

5. **Push and Create PR**:
```bash
git push origin feature/new-feature
# Create PR on GitHub
```

6. **Code Review**:
- Address review comments
- Update PR as needed

7. **Merge**:
- Squash and merge to `develop`
- Merge `develop` to `main` for releases

### Commit Messages

Follow conventional commits:
```
feat: Add image generation retry logic
fix: Fix guardrail violation detection
docs: Update API documentation
test: Add integration tests for workflow
refactor: Simplify state management
```

## Debugging

### Local Debugging

**VS Code Launch Configuration**:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: FastAPI",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/app/main.py",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload"],
      "jinja": true,
      "justMyCode": true
    }
  ]
}
```

### Celery Debugging

**Enable Debug Logging**:
```bash
celery -A app.celery_app worker --loglevel=debug
```

**Inspect Tasks**:
```python
from app.celery_app import celery_app
# Inspect active tasks
celery_app.control.inspect().active()
```

### Database Debugging

**Enable SQL Logging**:
```env
LOG_SQL=true
```

**Query Analysis**:
```python
from app.db.session import engine
# Enable query logging
engine.echo = True
```

## Performance Profiling

### API Profiling

**cProfile**:
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()
# Run code
profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

### Database Query Profiling

**SQLAlchemy Query Logging**:
```python
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

## Documentation

### Code Documentation

**Docstrings** (Google style):
```python
def story_writer_node(state: StoryState) -> dict:
    """Generate story text using LLM.
    
    Args:
        state: StoryState with prompt and age_group
        
    Returns:
        dict: Updated state with story_text and story_title
        
    Raises:
        StoryGenerationError: If generation fails
    """
    ...
```

### API Documentation

**FastAPI Auto-docs**:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

**Update Schemas**:
```python
from pydantic import BaseModel, Field

class StoryRequest(BaseModel):
    """Request to generate a story."""
    prompt: str = Field(..., description="Story prompt", max_length=5000)
    age_group: str = Field(..., description="Target age group")
```

## Common Tasks

### Adding a New Node

1. **Create Node File**:
```python
# app/agents/nodes/generation/my_node.py
def my_node(state: StoryState) -> dict:
    """My new node."""
    # Implementation
    return {"key": "value"}
```

2. **Register Node**:
```python
# app/agents/graph.py
from app.agents.nodes.generation.my_node import my_node

workflow.add_node("my_node", my_node)
```

3. **Add Edge**:
```python
workflow.add_edge("previous_node", "my_node")
```

### Adding a New API Endpoint

1. **Create Endpoint**:
```python
# app/api/stories.py
@router.get("/my-endpoint")
async def my_endpoint(db: AsyncSession = Depends(get_db)):
    """My new endpoint."""
    return {"message": "Hello"}
```

2. **Add Tests**:
```python
# tests/integration/test_api.py
def test_my_endpoint(client):
    response = client.get("/api/v1/stories/my-endpoint")
    assert response.status_code == 200
```

### Adding a New Guardrail Check

1. **Add Check Function**:
```python
# app/services/moderation.py
def check_my_guardrail(text: str) -> List[dict]:
    """Check for my guardrail violation."""
    violations = []
    # Implementation
    return violations
```

2. **Integrate in Node**:
```python
# app/agents/nodes/evaluation/story_guardrail.py
violations.extend(check_my_guardrail(story_text))
```

## Troubleshooting

### Common Issues

**Import Errors**:
- Check Python path
- Verify virtual environment is activated
- Check `__init__.py` files exist

**Database Connection Errors**:
- Verify DATABASE_URL is correct
- Check PostgreSQL is running
- Verify network connectivity

**Celery Task Not Running**:
- Check Celery worker is running
- Verify Redis connection
- Check task is registered

**Migration Errors**:
- Check migration file syntax
- Verify database schema matches models
- Test migration on development database first

## Resources

- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Celery Docs**: https://docs.celeryq.dev/
- **Alembic Docs**: https://alembic.sqlalchemy.org/

## Getting Help

- **GitHub Issues**: Open an issue for bugs or feature requests
- **Documentation**: Check `/docs` folder for detailed guides
- **Code Review**: Ask for code review on PRs
