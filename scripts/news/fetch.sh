#!/bin/bash
# Fetch agentic AI news from configured sources

set -euo pipefail

# Resolve ADJUTANT_DIR and load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/lockfiles.sh"
source "${COMMON}/logging.sh"
source "${COMMON}/platform.sh"

CONFIG_FILE="${ADJUTANT_DIR}/news_config.json"
STATE_DIR="${ADJUTANT_DIR}/state"
RAW_DIR="${STATE_DIR}/news_raw"
TODAY=$(date +%Y-%m-%d)
OUTPUT_FILE="${RAW_DIR}/${TODAY}.json"

# Helper: log to stderr and adjutant.log
nlog() { adj_log "news-fetch" "$*"; echo "[$(date +%H:%M:%S)] $*" >&2; }

# Check if killed
check_killed || exit 1

# Check if config exists
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Error: Configuration file not found: $CONFIG_FILE" >&2
  exit 1
fi

# Initialize output
ALL_ITEMS="[]"

# === Hacker News ===
fetch_hackernews() {
  if ! jq -e '.sources.hackernews.enabled == true' "$CONFIG_FILE" > /dev/null 2>&1; then
    return 0
  fi

  nlog "Fetching from Hacker News..."

  local max_items=$(jq -r '.sources.hackernews.max_items // 20' "$CONFIG_FILE")
  local lookback_hours=$(jq -r '.sources.hackernews.lookback_hours // 24' "$CONFIG_FILE")
  local keywords=$(jq -r '.keywords | join(" OR ")' "$CONFIG_FILE")
  
  # Calculate timestamp for lookback using platform.sh
  local timestamp
  timestamp=$(date_subtract_epoch "$lookback_hours" hours)

  local url="https://hn.algolia.com/api/v1/search?query=${keywords}&tags=story&numericFilters=created_at_i>${timestamp}&hitsPerPage=${max_items}"
  
  local items=$(curl -s "$url" | jq -c '[.hits[] | {
    title: .title,
    url: (.url // ("https://news.ycombinator.com/item?id=" + (.objectID | tostring))),
    score: (.points // 0),
    source: "hackernews",
    timestamp: (.created_at_i | todate)
  }]')
  
  echo "$items"
}

# === Reddit ===
fetch_reddit() {
  if ! jq -e '.sources.reddit.enabled == true' "$CONFIG_FILE" > /dev/null 2>&1; then
    return 0
  fi

  nlog "Fetching from Reddit..."

  local subreddits=$(jq -r '.sources.reddit.subreddits[]' "$CONFIG_FILE")
  local max_items=$(jq -r '.sources.reddit.max_items // 20' "$CONFIG_FILE")
  local keywords=$(jq -r '.keywords | map(gsub(" "; "+")) | join("+OR+")' "$CONFIG_FILE")
  
  local all_reddit_items="[]"
  
  while IFS= read -r subreddit; do
    nlog "  - r/${subreddit}..."
    
    local url="https://www.reddit.com/r/${subreddit}/search.json?q=${keywords}&restrict_sr=1&sort=new&t=day&limit=${max_items}"
    
    local items=$(curl -s -H "User-Agent: Adjutant/1.0" "$url" | jq -c '[.data.children[].data | {
      title: .title,
      url: .url,
      score: (.ups // 0),
      source: "reddit",
      timestamp: (.created_utc | todate)
    }]')
    
    all_reddit_items=$(echo "$all_reddit_items" | jq ". + $items")
  done <<< "$subreddits"
  
  echo "$all_reddit_items"
}

# === Company Blogs ===
fetch_blogs() {
  if ! jq -e '.sources.blogs.enabled == true' "$CONFIG_FILE" > /dev/null 2>&1; then
    return 0
  fi

  nlog "Fetching from company blogs..."

  local feeds=$(jq -c '.sources.blogs.feeds[]' "$CONFIG_FILE")
  local all_blog_items="[]"
  
  while IFS= read -r feed; do
    local name=$(echo "$feed" | jq -r '.name')
    local url=$(echo "$feed" | jq -r '.url')
    local type=$(echo "$feed" | jq -r '.type')
    
    nlog "  - ${name}..."
    
    if [[ "$type" == "html" ]]; then
      # Basic HTML scraping - extracts links from news pages
      # This is fragile but works for simple news listing pages
      local html=$(curl -s -L "$url")
      
      # Extract article links and titles
      # Pattern: look for <a> tags with href containing blog/news/article paths
      local items=$(echo "$html" | \
        grep -oi '<a[^>]*href="[^"]*"[^>]*>[^<]*</a>' | \
        grep -i 'news\|blog\|post\|article' | \
        head -10 | \
        sed -E 's|.*href="([^"]+)"[^>]*>([^<]+)</a>.*|{"url":"\1","title":"\2"}|' | \
        jq -c -s 'map({
          title: .title,
          url: (if .url | startswith("http") then .url else "'"$url"'" + .url end),
          score: 0,
          source: "blog:'"$name"'",
          timestamp: (now | todate)
        })')
      
      # If HTML scraping failed, try alternative: just return the main URL
      if [[ -z "$items" || "$items" == "[]" ]]; then
        items=$(echo "[{\"title\":\"${name} News\",\"url\":\"${url}\",\"score\":0,\"source\":\"blog:${name}\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}]")
      fi
      
      all_blog_items=$(echo "$all_blog_items" | jq ". + $items")

    elif [[ "$type" == "rss" ]]; then
      # RSS/Atom feed parsing via curl + XML extraction
      local xml=$(curl -s -L "$url")
      
      # Extract <item> or <entry> blocks and parse title + link
      # Handles both RSS 2.0 (<item>/<link>) and Atom (<entry>/<link href="">)
      local items=$(echo "$xml" | python3 -c "
import sys, json, re
from xml.etree import ElementTree as ET

xml = sys.stdin.read()
try:
    root = ET.fromstring(xml)
except ET.ParseError:
    print('[]')
    sys.exit(0)

ns = {'atom': 'http://www.w3.org/2005/Atom'}
items = []
source = '${name}'

# RSS 2.0
for item in root.findall('./channel/item')[:10]:
    title = item.findtext('title', '').strip()
    link  = item.findtext('link', '').strip()
    pub   = item.findtext('pubDate', '').strip()
    if title and link:
        items.append({'title': title, 'url': link, 'score': 0,
                      'source': 'rss:' + source, 'timestamp': pub or ''})

# Atom
for entry in root.findall('atom:entry', ns)[:10]:
    title = entry.findtext('atom:title', '', ns).strip()
    link_el = entry.find('atom:link', ns)
    link = (link_el.get('href', '') if link_el is not None else '').strip()
    pub  = entry.findtext('atom:published', '', ns).strip() or \
           entry.findtext('atom:updated', '', ns).strip()
    if title and link:
        items.append({'title': title, 'url': link, 'score': 0,
                      'source': 'rss:' + source, 'timestamp': pub or ''})

print(json.dumps(items))
")

      if [[ -z "$items" || "$items" == "[]" ]]; then
        nlog "  WARNING: no items parsed from RSS feed ${name}"
      fi

      all_blog_items=$(echo "$all_blog_items" | jq ". + ${items}")
    fi
  done <<< "$feeds"
  
  echo "$all_blog_items"
}

# === Main Orchestration ===
main() {
  nlog "Starting news fetch for ${TODAY}"
  
  # Fetch from all sources
  local hn_items=$(fetch_hackernews || echo "[]")
  local reddit_items=$(fetch_reddit || echo "[]")
  local blog_items=$(fetch_blogs || echo "[]")
  
  # Combine all items
  ALL_ITEMS=$(jq -s 'add' <(echo "$hn_items") <(echo "$reddit_items") <(echo "$blog_items"))
  
  # Write to file
  echo "$ALL_ITEMS" | jq '.' > "$OUTPUT_FILE"
  
  local count=$(echo "$ALL_ITEMS" | jq 'length')
  nlog "Fetched ${count} total items → ${OUTPUT_FILE}"
}

main
