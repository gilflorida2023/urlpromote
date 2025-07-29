#!/bin/bash
#export OLLAMA_HOST=192.168.0.8:11434
#if [[ -z "$OLLAMA_HOST" ]]
#then 
    #export OLLAMA_HOST=192.168.0.8:11434
#fi


echo "OLLAMA_HOST: ${OLLAMA_HOST:-192.168.0.8:11434}" >&2

# article2.sh - Article Summarization Tool
#
# Description:
#   Fetches and summarizes web articles using Ollama language models via API with caching
#
# Usage:
#   ./article2.sh <URL> [OLLAMA_MODEL] [SUMMARY_LENGTH] [OLLAMA_HOST]
#
# Dependencies:
#   curl, lynx, jq, stat



# Function to unload all Ollama models from memory
unload_ollama_models() {
    #local OLLAMA_HOST=$OLLAMA_HOST    #"${OLLAMA_HOST:-192.168.0.8:11434}"

    # Fetch loaded models (silently)
    local loaded_models
    loaded_models=$(curl -s "http://$OLLAMA_HOST/api/ps" | jq -r '.models[].name' 2>/dev/null)

    # Exit if no models loaded
    if [ -z "$loaded_models" ]; then
        echo "No models currently loaded." >&2
        return 0
    fi

    # Show loaded models if verbose
    echo "Found loaded models:" >&2
    echo "$loaded_models" | sed 's/^/  /' >&2

    # Process each model
    local unload_errors=0
    while read -r model; do
        echo -n "Unloading $model... " >&2

        # Unload request
        curl -s -X POST "http://$OLLAMA_HOST/api/generate" \
            -H "Content-Type: application/json" \
            -d '{"model": "'"$model"'", "prompt": "", "keep_alive": 0}' >/dev/null

        # Verify unload
        if curl -s "http://$OLLAMA_HOST/api/ps" | jq -e --arg model "$model" \
           'any(.models[]?.name; . == $model)' >/dev/null; then
            echo "❌" >&2
            ((unload_errors++))
        else
            echo "✅" >&2
        fi
    done <<< "$loaded_models"

    # Return status
    if [ $unload_errors -gt 0 ]; then
        echo "Warning: Failed to unload $unload_errors model(s)" >&2
        return 1
    else
        echo "All models unloaded successfully" >&2
        return 0
    fi
}


# Check for required arguments
if [ $# -lt 1 ]; then
  echo "Usage: $0 <URL> [OLLAMA_MODEL] [SUMMARY_LENGTH]" >&2
  exit 1
fi


# Configuration
URL="$1"
OLLAMA_MODEL="${2:-qwen2.5:14b}"
SUMMARY_LENGTH="${3:-257}"
export OLLAMA_HOST="${4:192.168.0.8:11434}"
SUMMARY_PROMPT="Respond ONLY with the ${SUMMARY_LENGTH}-character summary. No thinking output. Summary: $(cat <<'EOF'
Provide a concise summary of this article in exactly ${SUMMARY_LENGTH} characters or less (including spaces). 
Focus on key points and policy implications if any.
EOF
)"

unload_ollama_models
# Debug output
echo "Using model: $OLLAMA_MODEL" >&2
echo "Summary length: $SUMMARY_LENGTH" >&2

# Verify Ollama connection
check_ollama_server() {
  echo "Checking Ollama server status..." >&2
  if ! curl -s "http://${OLLAMA_HOST:-192.168.0.8:11434}/api/tags" >/dev/null; then
    echo "Error: Cannot connect to Ollama at ${OLLAMA_HOST:-192.168.0.8:11434}" >&2
    echo "Verify the server is running and accessible" >&2
    exit 1
  fi
  echo "Ollama server connection successful" >&2
}

# Verify model is available
check_model_available() {
  echo "Checking if model '$OLLAMA_MODEL' is available..." >&2
  if ! curl -s "http://${OLLAMA_HOST:-192.168.0.8:11434}/api/tags" | jq -e ".models[] | select(.name == \"$OLLAMA_MODEL\")" >/dev/null; then
    echo "Error: Model '$OLLAMA_MODEL' not found on server" >&2
    echo "Available models:" >&2
    curl -s "http://${OLLAMA_HOST:-192.168.0.8:11434}/api/tags" | jq -r '.models[].name' >&2
    exit 1
  fi
  echo "Model '$OLLAMA_MODEL' is available" >&2
}

check_ollama_server
check_model_available

# Cache setup
CACHE_DIR="${HOME}/.cache/article2"
mkdir -p "$CACHE_DIR"
URL_HASH=$(echo -n "$URL" | md5sum | awk '{print $1}')
CACHE_FILE="${CACHE_DIR}/${URL_HASH}.txt"

# Check dependencies
for cmd in curl lynx jq stat; do
  command -v $cmd &> /dev/null || { echo "Missing dependency: $cmd" >&2; exit 1; }
done

# Get article content with caching
if [ -f "$CACHE_FILE" ]; then
  current_time=$(date +%s)
  if stat -f %m "$CACHE_FILE" >/dev/null 2>&1; then
    file_mtime=$(stat -f %m "$CACHE_FILE")
  else
    file_mtime=$(stat -c %Y "$CACHE_FILE")
  fi
  
  cache_age_hours=$(( (current_time - file_mtime) / 3600 ))
  echo "Cache file age: ${cache_age_hours}h" >&2
  
  if [ $cache_age_hours -ge 24 ]; then
    echo "Refreshing expired cache..." >&2
    ARTICLE_CONTENT=$(curl -s -L "$URL" | lynx -dump -stdin -nolist -width=80)
    echo "$ARTICLE_CONTENT" > "$CACHE_FILE"
  else
    echo "Using cached content" >&2
    ARTICLE_CONTENT=$(cat "$CACHE_FILE")
  fi
else
  echo "Fetching new content..." >&2
  ARTICLE_CONTENT=$(curl -s -L "$URL" | lynx -dump -stdin -nolist -width=80)
  echo "$ARTICLE_CONTENT" > "$CACHE_FILE"
fi

# Clean thinking tags
clean_thinking() {
  sed -E '
    /<[Tt][Hh][Ii][Nn][Kk]>/I,/<\/[Tt][Hh][Ii][Nn][Kk]>/Id;
    /[Tt][Hh][Ii][Nn][Kk]\.\.\./I,/done thinking\./Id;
    /[Tt][Hh][Ii][Nn][Kk][Ii][Nn][Gg]\.\.\./I,/done thinking\./Id;
    /^[[:space:]]*(Thinking|THINKING)[[:space:]]*$/Id;
    /^[[:space:]]*$/d;
    s/^[[:space:]]+//;
    s/[[:space:]]+$//;
    ' | \
  tr -s ' '
}

# Generate summary via API
generate_summary() {
  local prompt="${SUMMARY_PROMPT}\n\n${ARTICLE_CONTENT}"
  echo "Generating summary (this may take a moment)..." >&2
  
  # Format prompt as JSON safely
  prompt_json=$(jq -n --arg prompt "$prompt" '$prompt')
  
  echo "Sending API request..." >&2
  response=$(curl -s -X POST "http://${OLLAMA_HOST:-192.168.0.8:11434}/api/generate" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg model "$OLLAMA_MODEL" --argjson prompt "$prompt_json" '{
      model: $model,
      prompt: $prompt,
      stream: false
    }')" 2>&1)
  
  if [ $? -ne 0 ]; then
    echo "API request failed" >&2
    echo "Error details: $response" >&2
    return 1
  fi
  
  if ! echo "$response" | jq -e '.response' >/dev/null; then
    echo "Invalid API response format" >&2
    echo "Raw response: $response" >&2
    return 1
  fi
  
  echo "$response" | jq -r '.response'
}

# Main summary generation
summary=$(generate_summary | clean_thinking)

# Fallback if empty
if [[ -z "$summary" || "$summary" =~ ^[[:space:]]*$ ]]; then
  echo "Warning: Empty summary received, using fallback content" >&2
  summary="[Error: No summary generated]"
fi

# Validate length
length=$(echo -n "$summary" | wc -m)
echo "Generated summary length: $length/$SUMMARY_LENGTH" >&2

if [ $length -gt $SUMMARY_LENGTH ]; then
  echo "Warning: Summary exceeded ${SUMMARY_LENGTH} characters ($length)" >&2
fi

# Final output (to stdout)
echo "$summary"
