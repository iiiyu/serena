# Serena Multi-Instance Support

Serena now supports running multiple instances simultaneously, allowing you to work with multiple projects at the same time in different Claude Code windows.

## Features

- **Multiple Projects**: Run separate Serena instances for different projects
- **Automatic Port Management**: Each instance gets its own ports (MCP and dashboard)
- **Instance Tracking**: View and manage all running instances
- **Process Isolation**: Each instance runs in its own process with separate language servers

## Usage

### Launch a New Instance

Launch a Serena instance for a specific project:

```bash
# Using stdio transport (for Claude Desktop)
uv run serena instances launch /path/to/project

# Using SSE transport with specific port
uv run serena instances launch /path/to/project --transport sse --port 8001

# With custom context and modes
uv run serena instances launch /path/to/project --context desktop-app --mode planning --mode editing

# Force replace existing instance for same project
uv run serena instances launch /path/to/project --force
```

### List Running Instances

View all currently running Serena instances:

```bash
# Human-readable format
uv run serena instances list

# JSON format for scripting
uv run serena instances list --json
```

Example output:
```
Found 2 running instance(s):

  PID: 12345
    Project: project1 (/home/user/projects/project1)
    Transport: sse (Port 8001), Dashboard: http://127.0.0.1:24282/dashboard/
    Context: desktop-app, Modes: planning, editing
    Uptime: 5m 30s

  PID: 12346
    Project: project2 (/home/user/projects/project2)
    Transport: stdio
    Context: ide-assistant, Modes: interactive
    Uptime: 2m 15s
```

### Kill Instances

Stop a specific instance by PID or project:

```bash
# Kill by PID
uv run serena instances kill 12345

# Kill by project name or path
uv run serena instances kill project1
uv run serena instances kill /home/user/projects/project1

# Kill all instances
uv run serena instances kill-all
uv run serena instances kill-all --yes  # Skip confirmation
```

## How It Works

1. **Instance Manager**: The `SerenaInstanceManager` class tracks all running instances in `~/.serena/instances.json`

2. **Port Allocation**: 
   - For SSE transport, ports are automatically assigned if not specified
   - Dashboard ports are automatically found starting from 0x5EDA (24282)
   - The system prevents port conflicts between instances

3. **Project Protection**: 
   - Only one instance per project is allowed by default
   - Use `--force` flag to replace an existing instance

4. **Process Management**:
   - Each instance runs as a separate process
   - Instances are tracked by PID
   - Dead instances are automatically cleaned up

## Integration with Claude Code

Claude Code has built-in support for running multiple instances with different projects. Each project can have its own Serena configuration.

### Method 1: Using Claude Code's Built-in MCP Management (Recommended)

Claude Code automatically manages separate MCP server instances for each project. Simply configure Serena for each project:

#### Step 1: Configure Serena for Each Project

Navigate to each project directory and add Serena as an MCP server:

```bash
# For project 1 - Frontend
cd ~/projects/frontend
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd)

# For project 2 - Backend  
cd ~/projects/backend
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd)

# For project 3 - API with custom modes
cd ~/projects/api
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd) --mode planning --mode editing
```

If you have Serena installed locally, you can use:

```bash
cd ~/projects/frontend
claude mcp add serena -- uv run --directory /path/to/serena serena start-mcp-server --context ide-assistant --project $(pwd)
```

#### Step 2: Start Claude Code for Each Project

Open separate terminal windows/tabs and start Claude Code in each project:

```bash
# Terminal 1
cd ~/projects/frontend
claude code

# Terminal 2 (new terminal window/tab)
cd ~/projects/backend
claude code

# Terminal 3 (new terminal window/tab)
cd ~/projects/api
claude code
```

#### Step 3: Work with Multiple Projects

Now you have:
- **Separate Claude Code windows** for each project
- **Isolated Serena instances** with project-specific language servers
- **Independent contexts** - no interference between projects
- **Cached language servers** per project for better performance

Each Claude Code window will automatically:
- Start its own Serena MCP server instance
- Connect to the project-specific configuration
- Maintain separate state and memory

#### Step 4: Verify Configuration

You can verify the MCP configuration for each project:

```bash
# Check MCP servers configured for a project
cd ~/projects/frontend
claude mcp list

# Should show:
# serena: uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project /home/user/projects/frontend
```

#### Step 5: Update or Remove Configuration

If you need to update the Serena configuration for a project:

```bash
# Remove existing configuration
claude mcp remove serena

# Add with new configuration
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context desktop-app --project $(pwd) --mode interactive
```

### Method 2: Using the Instance Manager (Alternative)

For more control over instance lifecycle, you can use Serena's instance manager:

```bash
# Launch instances manually
uv run serena instances launch ~/projects/frontend --transport sse --port 8001
uv run serena instances launch ~/projects/backend --transport sse --port 8002

# List running instances
uv run serena instances list

# Kill instances when done
uv run serena instances kill-all --yes
```

Then configure Claude Code to connect to specific ports:

```bash
cd ~/projects/frontend
claude mcp add serena-frontend -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --transport sse --port 8001

cd ~/projects/backend
claude mcp add serena-backend -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --transport sse --port 8002
```

### Best Practices

1. **Use the ide-assistant context**: It's optimized for Claude Code integration
   ```bash
   --context ide-assistant
   ```

2. **Always specify the project path**: This ensures proper project activation
   ```bash
   --project $(pwd)
   ```

3. **Index large projects**: Speed up Serena's performance
   ```bash
   uvx --from git+https://github.com/oraios/serena serena project index
   ```

4. **Use project-specific modes**: Customize behavior per project
   ```bash
   --mode planning --mode editing  # For new feature development
   --mode interactive  # For exploratory work
   ```

5. **Monitor resource usage**: Each instance runs its own language server
   - Check memory usage with `ps aux | grep serena`
   - Close unused Claude Code windows to free resources

### Convenience Script

Create a helper script to quickly launch Claude Code with Serena:

```bash
#!/bin/bash
# ~/bin/claude-serena

# Usage: claude-serena [project-path] [context] [modes...]

PROJECT="${1:-$(pwd)}"
CONTEXT="${2:-ide-assistant}"
shift 2
MODES=""
for mode in "$@"; do
    MODES="$MODES --mode $mode"
done

cd "$PROJECT"

# Add Serena MCP server for this project
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena \
    serena start-mcp-server --context "$CONTEXT" --project "$PROJECT" $MODES

# Start Claude Code
claude code
```

Use it like:
```bash
claude-serena ~/projects/frontend
claude-serena ~/projects/backend ide-assistant planning editing
claude-serena . desktop-app interactive
```

### Troubleshooting

1. **If Serena doesn't start**: Check if another instance is already running for the same project
   ```bash
   uv run serena instances list
   ```

2. **Port conflicts**: Use different ports for SSE transport or stick with stdio (default)

3. **Clean up stale processes**: Claude Code should manage this automatically, but if needed:
   ```bash
   ps aux | grep serena
   kill <PID>
   ```

4. **View logs**: Check Serena's dashboard at `http://localhost:24282/dashboard/` (port may vary)

## Architecture

The multi-instance support is implemented through:

- **`instance_manager.py`**: Core instance management logic
- **`cli.py`**: New `instances` command group for CLI interface
- **Port isolation**: Each instance gets unique ports
- **Process tracking**: PID-based instance lifecycle management
- **Persistent state**: Instance information stored in JSON file

## Limitations

- Each project can only have one active instance (unless using `--force`)
- SSE transport requires explicit port specification to avoid conflicts
- Dashboard port estimation may not be exact (actual port is auto-discovered)

## Troubleshooting

If an instance fails to start:
1. Check if a port is already in use
2. Verify the project path exists
3. Check logs in `~/.serena/logs/`
4. Ensure no stale instances with `uv run serena instances list`

If instances appear stuck:
1. Use `uv run serena instances kill-all --yes` to clean up
2. Check for zombie processes with `ps aux | grep serena`
3. Remove stale entries from `~/.serena/instances.json` if needed