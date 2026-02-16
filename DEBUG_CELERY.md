# Debugging Celery Tasks

This guide provides multiple approaches to debug Celery tasks in this project.

## Option 1: Remote Debugging with debugpy (Recommended)

This is the most reliable method for hitting breakpoints in your IDE.

### Setup:

1. **Install debugpy** (already in requirements.txt):
   ```bash
   pip install debugpy
   ```

2. **Start Celery with debugpy in Docker**:
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.debug.yml up celery
   ```
   
   The container will wait for a debugger to attach (due to `--wait-for-client`).

3. **Attach your IDE debugger**:
   
   **VS Code:**
   - Open the Run and Debug panel (Cmd+Shift+D)
   - Select "Python: Remote Attach (Celery)"
   - Click the play button
   - Set your breakpoints in the code
   - Trigger a Celery task
   
   **PyCharm:**
   - Go to Run → Edit Configurations
   - Add new "Python Debug Server"
   - Set host: `localhost`, port: `5679`
   - Start the debug server
   - Set breakpoints and trigger tasks

### Advantages:
- ✅ Breakpoints work reliably
- ✅ Full IDE debugging features
- ✅ Can inspect variables, step through code
- ✅ Works with Docker

## Option 2: Run Celery Locally (Outside Docker)

This allows you to debug directly without Docker complications.

### Setup:

1. **Ensure dependencies are installed locally**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start required services** (PostgreSQL, Redis):
   ```bash
   docker-compose up postgres redis
   ```

3. **Run Celery locally**:
   ```bash
   chmod +x run_celery_debug.sh
   ./run_celery_debug.sh
   ```
   
   Or manually:
   ```bash
   celery -A app.celery_app worker --pool=solo --loglevel=debug --concurrency=1
   ```

4. **Set breakpoints in your IDE** and they should work directly.

### Advantages:
- ✅ Simplest setup
- ✅ No Docker networking issues
- ✅ Direct IDE integration
- ✅ Faster iteration

### Disadvantages:
- ❌ Need to install dependencies locally
- ❌ Need to ensure environment variables match

## Option 3: Use pdb/ipdb for Interactive Debugging

Add breakpoints directly in your code using `pdb` or `ipdb`.

### Setup:

1. **Add breakpoint in your code**:
   ```python
   import ipdb; ipdb.set_trace()
   ```
   
   Or use the built-in breakpoint():
   ```python
   breakpoint()  # Python 3.7+
   ```

2. **Run Celery with pdb support**:
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.debug.yml up celery
   ```
   
   Or modify the command in `docker-compose.debug.yml` to use Option 2 (without debugpy).

3. **Attach to the container**:
   ```bash
   docker exec -it kids_story_celery /bin/bash
   ```

4. **When breakpoint hits**, you'll see an interactive debugger in the terminal.

### Advantages:
- ✅ No IDE setup needed
- ✅ Works in any environment
- ✅ Good for quick debugging

### Disadvantages:
- ❌ Terminal-based (less convenient than IDE)
- ❌ Need to attach to container

## Option 4: Enhanced Logging

If breakpoints aren't working, use detailed logging to trace execution.

### Setup:

1. **The debug compose file already sets `LOG_LEVEL=debug`**

2. **Add detailed logging in your tasks**:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   
   @celery_app.task(bind=True, name="generate_story_task")
   def generate_story_task(self, job_id: str):
       logger.debug(f"Task started with job_id: {job_id}")
       logger.debug(f"Task ID: {self.request.id}")
       # Your code here
       logger.debug("About to call async function")
       result = asyncio.run(_generate_story_async(job_id, task_id))
       logger.debug(f"Task completed with result: {result}")
       return result
   ```

3. **View logs**:
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.debug.yml logs -f celery
   ```

## Troubleshooting

### Breakpoints not hitting?

1. **Check that source code is mounted**:
   ```bash
   docker exec -it kids_story_celery ls -la /app
   ```
   Should show your source files.

2. **Verify Celery is using solo pool**:
   Check logs for: `pool=solo`

3. **Check debugpy is listening**:
   ```bash
   docker exec -it kids_story_celery netstat -an | grep 5679
   ```

4. **Try running locally** (Option 2) - this eliminates Docker issues.

### Debugger won't attach?

1. **Check port is exposed**:
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.debug.yml ps
   ```
   Should show port `5679:5679` for celery service.

2. **Check firewall** - ensure port 5679 is accessible.

3. **Try without `--wait-for-client`** - remove it from the command and attach quickly after starting.

## Quick Reference

| Method | Command | Best For |
|--------|---------|----------|
| Remote Debug (Docker) | `docker-compose -f docker-compose.yml -f docker-compose.debug.yml up celery` | Full IDE debugging in Docker |
| Local Debug | `./run_celery_debug.sh` | Simplest setup, direct IDE integration |
| pdb/ipdb | Add `breakpoint()` in code | Quick debugging, no IDE needed |
| Logging | Already enabled with `LOG_LEVEL=debug` | Tracing execution flow |
