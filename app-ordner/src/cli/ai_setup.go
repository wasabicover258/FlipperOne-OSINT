package main

import (
 "os"
 "strings"
)

func runAIStatus(){
 head("AI & web research setup")
 info("Built-in evidence ranking: ready (offline, no key).")
 if strings.TrimSpace(os.Getenv("BRAVE_SEARCH_API_KEY"))!="" {
  found("Broad web/PDF search: Brave API configured")
 } else {
  info("Broad web/PDF search: configure Brave Search API key.")
  info("Without a key: Wikipedia + OpenAlex still work.")
 }
 if strings.TrimSpace(os.Getenv("AI_CHAT_MODEL"))!="" &&
    validAIEndpoint(strings.TrimSpace(os.Getenv("AI_CHAT_URL"))) {
  found("Generative summaries: model endpoint configured")
 } else {
  info("Generative AI: optional; local NLP ranking works without it.")
  info("Use a local llama.cpp /v1/chat/completions server")
  info("or a supported HTTPS OpenAI-compatible API.")
 }
 info("Configuration file: ~/.config/flipperone-osint/ai.env")
 info("Keys are never displayed here or saved in a case report.")
}
