#!/bin/bash

# allmodels.sh - Ollama Model Testing Framework
#
# Description:
#   Tests all available Ollama models with a given article URL and records performance metrics.
#
# Usage:
#   ./allmodels.sh
#
# Features:
#   - Automatically tests all installed Ollama models
#   - Measures execution time for each model
#   - Logs results to output.txt
#   - Includes error handling and model cleanup
#
# Dependencies:
#   - ollama - For model management
#   - article2.sh - For article summarization
#
# Output Files:
#   - output.txt - Contains detailed test results
#
# Exit Codes:
#   0 - Success
#   1 - Error in model testing
#
# Examples:
#   ./allmodels.sh


format_elapsed() {
    local seconds=$1
    local days=$((seconds / 86400))
    local hours=$((seconds % 86400 / 3600))
    local minutes=$((seconds % 3600 / 60))
    local secs=$((seconds % 60))

    if [ $days -gt 0 ]; then
        printf "%dd %dh %dm %ds" $days $hours $minutes $secs
    elif [ $hours -gt 0 ]; then
        printf "%dh %dm %ds" $hours $minutes $secs
    elif [ $minutes -gt 0 ]; then
        printf "%dm %ds" $minutes $secs
    else
        printf "%ds" $secs
    fi
}

ollama_list_models() {
    ollama list | sed -e 's/\ .*//' | sed -e '1d' |sort
}

# Define your skip list (space-separated)
# This is the list of models that dont follow my instructions.
# will perform aother run and compare what is left.
export SKIP_LIST="deepcoder:14b deepcoder:1.5b deepscaler:1.5b deepseek-r1:14b deepseek-r1:1.5b deepseek-r1:32b deepseek-r1:7b deepseek-r1:8b devstral:24b gemma3:1b gemma3:27b gemma3n:e2b gemma3n:e4b granite3.2-vision:2b granite3.2-vision-abliterated:2b granite3.3:2b granite3.3:2b-base granite3.3:8b granite3.3:8b-base huihui_ai/granite3.2-vision-abliterated:2b huihui_ai/magistral-abliterated:24b ibm/granite3.3:2b-base ibm/granite3.3:8b-base llava:7b magistral:24b magistral-abliterated:24bi minicpm-v:8b mistral-small3.1:24b mistral-small3.2:24b mistral-small3.2:24bi phi4-mini-reasoning:3.8b phi4-reasoning:latest qwen2.5:0.5b qwen2.5:1.5b qwen2.5:7b qwen3:30b qwen2.5:32b qwen2.5vl:32b qwen2.5vl:3b qwen2.5vl:7b qwen3:0.6b qwen3:14b qwen3:1.7b qwen3:32b qwen3:4b qwen3:8b qwq:latest"

ollama_list_edited() {
    # Check if skip list is non-empty
    if [[ -z "$SKIP_LIST" ]]; then
        ollama_list_models
    else
        # Convert space-separated list to grep pattern
        pattern=$(echo "$SKIP_LIST" | tr ' ' '|')
        ollama_list_models | grep -vE "$pattern"
    fi
}

ollama_stop_all() {
     echo "Stopping all running Ollama models..."
     ollama ps | awk 'NR>1 {print $1}' | xargs -I{} ollama stop {}
     echo "All models stopped"
}

# Clear previous output
ollama_stop_all
#URL="https://www.theverge.com/tesla/712703/tesla-robotaxi-fsd-elon-musk-earnings-q2-2025"
#URL="https://www.businessinsider.com/grok-chatbot-rudi-kids-elon-musk-i-tried-why-2025-7"
#URL="https://www.rt.com/news/621830-trump-seeking-spacex-alternative/"

#URL="https://www.ibtimes.co.uk/roller-skates-superchargers-optimus-serving-popcorn-whats-really-inside-elon-musks-tesla-1739015"
#URL="https://metro.co.uk/2025/07/22/south-park-scores-groundbreaking-1-500-000-000-deal-fans-vow-cancel-streaming-subscriptions-23720220/"
#URL="https://www.dailymail.co.uk/columnists/article-14940875/Now-South-Park-mocking-Trump-Epstein-knows-hes-facing-scandal-control-ANDREW-NEIL.html?ns_mchannel=rss&ns_campaign=1490&ito=1490"
URL="https://www.tmz.com/2025/07/25/ghislaine-maxwell-talks-100-names-linked-jeffrey-epstein-feds-interview-immunity/"
rm -f output.txt
# Main testing loop
for model in $(ollama_list_edited); do
    echo "---------------------------------" | tee -a output.txt
    echo "Testing model: $model" | tee -a output.txt
    
    stime=$(date '+%s')
    bash article2.sh "$URL" "$model" | tee -a output.txt
    exit_code=$?
    etime=$(date '+%s')
    
    elapsed=$((etime - stime))
    formatted_time=$(format_elapsed $elapsed)
    
    echo "Execution time: $formatted_time" | tee -a output.txt
    
    # Check for errors
    if [ $exit_code -ne 0 ]; then
        echo "WARNING: Model $model failed with exit code $exit_code" | tee -a output.txt
    fi
    
    ollama_stop_all
done

echo -e "\nTesting complete. Results saved to:"
echo "  - output.txt"
