#!/bin/bash

# article2.sh - Article Summarization Tool
#
# Description:
#   Fetches and summarizes web articles using Ollama language models with caching functionality.
#
# Usage:
#   ./article2.sh <URL> [OLLAMA_MODEL] [SUMMARY_LENGTH]
#
# Parameters:
#   URL            - The URL of the article to summarize (required)
#   OLLAMA_MODEL   - The Ollama model to use for summarization (default: qwen2.5:3b)
#   SUMMARY_LENGTH - Maximum length of summary (default: 257)
#
# Features:
#   - Article content caching (stored in ~/.cache/article2/)
#   - Automatic content extraction using lynx
#   - Configurable character limit for summaries
#   - Thinking tag removal from model output
#   - Character count validation
#   - 24-hour cache expiration
#
# Dependencies:
#   - curl - For fetching web content
#   - lynx - For HTML to text conversion
#   - ollama - For running language models
#   - stat - For cache age checking
#
# Exit Codes:
#   0 - Success
#   1 - Missing arguments or dependencies
#
# Examples:
#   ./article2.sh https://example.com/article
#   ./article2.sh https://example.com/article llama2-uncensored
#   ./article2.sh https://example.com/article mistral-small3.1:24b 280

# Check for required arguments
if [ $# -lt 1 ]; then
  echo "Usage: $0 <URL> [OLLAMA_MODEL] [SUMMARY_LENGTH]"
  exit 1
fi

ollama_stop_all 2>&1 >/dev/null

# Configuration
URL="$1"
OLLAMA_MODEL="${2:-qwen2.5:3b}"
SUMMARY_LENGTH="${3:-257}"
SUMMARY_PROMPT="Respond ONLY with the ${SUMMARY_LENGTH}-character summary. No thinking output. Summary: $(cat <<'EOF'
Provide a concise summary of this article in exactly ${SUMMARY_LENGTH} characters or less (including spaces). 
Focus on key points and policy implications if any.
EOF
)"

# Cache setup
CACHE_DIR="${HOME}/.cache/article2"
mkdir -p "$CACHE_DIR"
URL_HASH=$(echo -n "$URL" | md5sum | awk '{print $1}')
CACHE_FILE="${CACHE_DIR}/${URL_HASH}.txt"

# Check dependencies
for cmd in curl lynx ollama stat; do
  command -v $cmd &> /dev/null || { echo "Missing $cmd"; exit 1; }
done

# Get article content with reliable cache expiration
if [ -f "$CACHE_FILE" ]; then
  # Get current timestamp
  current_time=$(date +%s)
  
  # Get modification time (cross-platform)
  if stat -f %m "$CACHE_FILE" >/dev/null 2>&1; then  # BSD/macOS
    file_mtime=$(stat -f %m "$CACHE_FILE")
  else  # Linux
    file_mtime=$(stat -c %Y "$CACHE_FILE")
  fi
  
  # Calculate age in hours
  cache_age_hours=$(( (current_time - file_mtime) / 3600 ))
  
  # Refresh if older than 24 hours
  if [ $cache_age_hours -ge 24 ]; then
    #echo "Cache expired (${cache_age_hours}h old), refreshing..."
    ARTICLE_CONTENT=$(curl -s -L "$URL" | lynx -dump -stdin -nolist -width=80)
    echo "$ARTICLE_CONTENT" > "$CACHE_FILE"
  else
    #echo "Using cached content (${cache_age_hours}h old)..."
    ARTICLE_CONTENT=$(cat "$CACHE_FILE")
  fi
else
  #echo "No cache found - fetching from $URL..."
  ARTICLE_CONTENT=$(curl -s -L "$URL" | lynx -dump -stdin -nolist -width=80)
  echo "$ARTICLE_CONTENT" > "$CACHE_FILE"
fi

# Universal thinking tag remover
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

# Generate summary
summary=$(
  {
    echo "$ARTICLE_CONTENT" | \
    ollama run $OLLAMA_MODEL "$SUMMARY_PROMPT" 2>/dev/null || \
    echo "$ARTICLE_CONTENT" | ollama run $OLLAMA_MODEL "$SUMMARY_PROMPT"
  } | clean_thinking
)

# Verify output
if [[ -z "$summary" || "$summary" =~ ^[[:space:]]*$ ]]; then
  summary="[Error: No summary generated]"
fi

# Final output
length=$(echo -n "$summary" | wc -m)
#echo -e "\nCharacter count: $length/${SUMMARY_LENGTH}; Model Name: $OLLAMA_MODEL"
if [ $length -gt $SUMMARY_LENGTH ]; then
  echo -e "\nReject: Summary exceeded ${SUMMARY_LENGTH} characters ($length). Consider using a more precise model."
#else
  #echo -e "\nAccept: Summary within ${SUMMARY_LENGTH} characters ($length)."
fi
echo -e "$summary"
