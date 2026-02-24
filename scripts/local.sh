#!/bin/bash

# Local/Offline Investigation Script
# Scans local repos on disk, analyses with Claude, saves results locally
# Generates Mermaid diagrams when CREATE_DIAGRAMS=true in .env.local
#
# Prerequisites: Temporal server (mise dev-server) and worker (mise dev-worker) must be running
# Or this script will start them automatically.

# Always load .env.local file for local testing
if [ -f ".env.local" ]; then
    echo "📂 Loading configuration from .env.local..."
    set -a  # Export all variables
    source .env.local
    set +a  # Stop exporting
    echo "✅ Loaded .env.local"
else
    echo "⚠️  Warning: .env.local not found, using default local settings"
    export PROMPT_CONTEXT_STORAGE=file
    export SKIP_DYNAMODB_CHECK=true
    export LOCAL_TESTING=true
fi

echo "Setting up Local/Offline Investigation Workflow..."
echo "📝 Environment configured:"
echo "   PROMPT_CONTEXT_STORAGE=${PROMPT_CONTEXT_STORAGE:-file}"
echo "   SKIP_DYNAMODB_CHECK=${SKIP_DYNAMODB_CHECK:-true}"
echo "   LOCAL_TESTING=${LOCAL_TESTING:-true}"
echo "   CREATE_DIAGRAMS=${CREATE_DIAGRAMS:-false}"
echo "   RENDER_MERMAID_PNGS=${RENDER_MERMAID_PNGS:-false}"
echo "   LOCAL_OUTPUT_DIR=${LOCAL_OUTPUT_DIR:-outputs}"
echo ""

uv sync

# Check if API key is set (only required when AI mode is enabled)
if [[ "${ENABLE_AI}" == "false" ]]; then
    echo "🔧 ENABLE_AI=false -- static analysis mode (no Claude API key required)"
else
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        echo "❌ Error: ANTHROPIC_API_KEY environment variable is not set"
        echo "Please set your Claude API key in .env.local:"
        echo "ANTHROPIC_API_KEY=your-api-key-here"
        echo "Or set ENABLE_AI=false for static analysis mode (no API key needed)"
        exit 1
    fi
fi

if [[ "${CREATE_DIAGRAMS}" != "true" ]]; then
    echo "⚠️  CREATE_DIAGRAMS is not set to true in .env.local"
    echo "   Mermaid diagrams will NOT be generated."
    echo "   Set CREATE_DIAGRAMS=true in .env.local to enable diagram generation."
    echo ""
fi

echo "🏠 Starting LOCAL investigation workflow..."
echo "This will scan local repos (configured via file:// URIs in repos.json)"
echo ""

# Parse positional arguments for configuration overrides
FORCE_FLAG=""
CLAUDE_MODEL=""
MAX_TOKENS=""
CHUNK_SIZE=""
OUTPUT_DIR=""

i=1
while [ $i -le $# ]; do
    arg="${!i}"
    case $arg in
        force)
            echo "⚡ FORCE MODE ENABLED - all repositories will be investigated regardless of cache!"
            FORCE_FLAG="--force"
            ;;
        model)
            i=$((i + 1))
            if [ $i -le $# ]; then
                CLAUDE_MODEL="${!i}"
                echo "🔧 Claude model override: $CLAUDE_MODEL"
            else
                echo "❌ Error: 'model' requires a model name argument"
                exit 1
            fi
            ;;
        max-tokens)
            i=$((i + 1))
            if [ $i -le $# ]; then
                MAX_TOKENS="${!i}"
                echo "🔧 Max tokens override: $MAX_TOKENS"
            else
                echo "❌ Error: 'max-tokens' requires a number argument"
                exit 1
            fi
            ;;
        chunk-size)
            i=$((i + 1))
            if [ $i -le $# ]; then
                CHUNK_SIZE="${!i}"
                echo "🔧 Chunk size override: $CHUNK_SIZE"
            else
                echo "❌ Error: 'chunk-size' requires a number argument"
                exit 1
            fi
            ;;
        output-dir)
            i=$((i + 1))
            if [ $i -le $# ]; then
                OUTPUT_DIR="${!i}"
                echo "📁 Output directory override: $OUTPUT_DIR"
            else
                echo "❌ Error: 'output-dir' requires a directory argument"
                exit 1
            fi
            ;;
        dry-run)
            echo "🧪 DRY RUN MODE - will not execute full workflow"
            DRY_RUN=true
            ;;
        h)
            echo "📚 Local/Offline Investigation Workflow Help"
            echo ""
            echo "Usage: mise investigate-local [ARGUMENTS]"
            echo ""
            echo "Scans local repos on disk, analyses with Claude, saves results locally."
            echo "Generates Mermaid diagrams when CREATE_DIAGRAMS=true in .env.local."
            echo ""
            echo "Prerequisites:"
            echo "  1. Temporal server running:  mise dev-server   (terminal 1)"
            echo "  2. Worker running:           mise dev-worker   (terminal 2)"
            echo "  3. Repos configured with file:// URIs in prompts/repos.json"
            echo "  4. CREATE_DIAGRAMS=true in .env.local (for diagram generation)"
            echo ""
            echo "Arguments (can be used in any order):"
            echo "  force                                    Forces investigation of all repos ignoring cache"
            echo "  model MODEL_NAME                         Override Claude model to use"
            echo "  max-tokens NUMBER                        Override max tokens (100-100000)"
            echo "  chunk-size NUMBER                        Override number of repos to process in parallel (1-20)"
            echo "  output-dir DIR                           Override output directory (default: outputs)"
            echo "  dry-run                                  Show what would be executed without running"
            echo "  h                                        Show this help message"
            echo ""
            echo "Examples:"
            echo "  mise investigate-local                              # Default settings"
            echo "  mise investigate-local force                        # Force investigation"
            echo "  mise investigate-local chunk-size 4                 # Process 4 repos in parallel"
            echo "  mise investigate-local force output-dir my-output   # Force with custom output dir"
            echo ""
            echo "Output:"
            echo "  outputs/{repo-name}-arch.md              Per-repo analysis files"
            echo "  outputs/diagrams/architecture-overview.md Cross-repo Mermaid diagrams"
            echo ""
            echo "Note: Requires file:// URIs set for repos in prompts/repos.json:"
            echo '  "my-repo": { "uri": "file:///path/to/repo", "type": "backend" }'
            echo ""
            exit 0
            ;;
        *)
            echo "⚠️  Warning: Unknown argument '$arg' ignored"
            echo "💡 Use 'mise investigate-local h' to see available options"
            ;;
    esac
    i=$((i + 1))
done

# Build arguments for client
CLIENT_ARGS="$FORCE_FLAG"
if [[ -n "$CLAUDE_MODEL" ]]; then
    CLIENT_ARGS="$CLIENT_ARGS --claude-model=$CLAUDE_MODEL"
fi
if [[ -n "$MAX_TOKENS" ]]; then
    CLIENT_ARGS="$CLIENT_ARGS --max-tokens=$MAX_TOKENS"
fi
if [[ -n "$CHUNK_SIZE" ]]; then
    CLIENT_ARGS="$CLIENT_ARGS --chunk-size=$CHUNK_SIZE"
fi
if [[ -n "$OUTPUT_DIR" ]]; then
    CLIENT_ARGS="$CLIENT_ARGS --output-dir=$OUTPUT_DIR"
fi

# Check if dry-run mode before starting services
if [[ "$DRY_RUN" == "true" ]]; then
    echo "🧪 DRY RUN - Would execute: python -m client investigate-local $CLIENT_ARGS"
    echo "Final parsed values:"
    echo "  FORCE_FLAG: '$FORCE_FLAG'"
    echo "  CLAUDE_MODEL: '$CLAUDE_MODEL'"
    echo "  MAX_TOKENS: '$MAX_TOKENS'"
    echo "  CHUNK_SIZE: '$CHUNK_SIZE'"
    echo "  OUTPUT_DIR: '$OUTPUT_DIR'"
    echo "  CREATE_DIAGRAMS: '${CREATE_DIAGRAMS:-false}'"
    echo "✅ DRY RUN completed - no services started"
    exit 0
fi

# Ensure environment variables are exported
export PROMPT_CONTEXT_STORAGE=${PROMPT_CONTEXT_STORAGE:-file}
export SKIP_DYNAMODB_CHECK=${SKIP_DYNAMODB_CHECK:-true}
export LOCAL_TESTING=${LOCAL_TESTING:-true}

echo "🔧 Environment:"
echo "   PROMPT_CONTEXT_STORAGE=$PROMPT_CONTEXT_STORAGE"
echo "   SKIP_DYNAMODB_CHECK=$SKIP_DYNAMODB_CHECK"
echo "   CREATE_DIAGRAMS=${CREATE_DIAGRAMS:-false}"
echo "   RENDER_MERMAID_PNGS=${RENDER_MERMAID_PNGS:-false}"
echo "   LOCAL_OUTPUT_DIR=${LOCAL_OUTPUT_DIR:-outputs}"
echo ""

# Run the client with investigate-local command
cd src && python -m client investigate-local $CLIENT_ARGS

echo ""
echo "✅ Local investigation workflow completed!"
echo "Check the ${LOCAL_OUTPUT_DIR:-outputs}/ directory for per-repo analysis files."
if [[ "${CREATE_DIAGRAMS}" == "true" ]]; then
    echo "Check the ${LOCAL_OUTPUT_DIR:-outputs}/diagrams/ directory for Mermaid diagrams."
    if [[ "${RENDER_MERMAID_PNGS}" == "true" ]]; then
        echo "Check the ${LOCAL_OUTPUT_DIR:-outputs}/diagrams/ directory for rendered PNG files."
    fi
fi
