import time
import json
import uuid
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

app = FastAPI()

# --- Configuration ---
# 1. Set your proprietary model's limit here so we can report it to Cline if needed
MAX_CONTEXT = 32768 

# --- Pydantic Models for Validation ---
class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "custom-model"
    messages: List[Message]
    stream: bool = False
    temperature: Optional[float] = 0.7
    stop: Optional[List[str]] = None # Cline sends ["</function_calls>"] etc.

# --- MOCK Proprietary API Call ---
# Replace this function with your actual API call
def call_proprietary_llm(prompt: str, stop_sequences: List[str]):
    """
    Simulates a proprietary generator that yields text chunks.
    You would replace this with: yield from my_custom_client.stream(prompt)
    """
    # specific text for testing cline
    full_response = "I am a custom model. I see your code. <function_calls>"
    
    for word in full_response.split(" "):
        yield word + " "
        time.sleep(0.05) 

# --- Helper: Convert Messages to Prompt ---
def format_prompt(messages: List[Message]) -> str:
    """
    Cline relies on a 'System' prompt. If your model doesn't support it, 
    we must merge it into the User prompt.
    """
    formatted_prompt = ""
    for msg in messages:
        # HACK: Force 'system' messages to be part of the text for models that ignore system roles
        if msg.role == "system":
            formatted_prompt += f"Instructions: {msg.content}\n\n"
        elif msg.role == "user":
            formatted_prompt += f"User: {msg.content}\n"
        elif msg.role == "assistant":
            formatted_prompt += f"Assistant: {msg.content}\n"
            
    formatted_prompt += "Assistant: "
    return formatted_prompt

# --- Core Endpoint ---
@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    
    # 1. Handle Context/Prompt Formatting
    prompt = format_prompt(request.messages)
    
    # 2. Generate a unique ID (Cline likes to track this)
    request_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    # 3. Define the Stream Generator
    async def stream_generator():
        # A. Send the "Role" chunk first (Best practice for OpenAI compatibility)
        yield f"data: {json.dumps({
            'id': request_id, 'object': 'chat.completion.chunk', 'created': created_time, 'model': request.model,
            'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]
        })}\n\n"

        current_text = ""
        token_count = 0

        # B. Stream content from your proprietary model
        for chunk_text in call_proprietary_llm(prompt, request.stop or []):
            token_count += 1
            current_text += chunk_text
            
            # CHECK STOP SEQUENCES MANUALLY
            # (If your proprietary API doesn't handle stop sequences, you must buffer and check here)
            # For this simple example, we pass it through, but you might need a buffer logic here.

            chunk_data = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": request.model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": chunk_text},
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(chunk_data)}\n\n"

        # C. CRITICAL: Send Usage Statistics
        # Cline calculates context based on this. If missing, context window breaks.
        # We estimate 1 word ~= 1.3 tokens if you don't have a real tokenizer.
        prompt_tokens = len(prompt.split()) 
        completion_tokens = token_count
        
        usage_data = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": request.model,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }],
            # ADD THIS FIELD or Cline will fail to track context limits
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens
            }
        }
        yield f"data: {json.dumps(usage_data)}\n\n"
        yield "data: [DONE]\n\n"

    # 4. Return Streaming Response
    if request.stream:
        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    # 5. Handle Non-Streaming (Fallback)
    else:
        # Collect all text
        full_response = ""
        for chunk in call_proprietary_llm(prompt, request.stop or []):
            full_response += chunk
            
        return JSONResponse({
            "id": request_id,
            "object": "chat.completion",
            "created": created_time,
            "model": request.model,
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(full_response.split()),
                "total_tokens": len(prompt.split()) + len(full_response.split())
            },
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": full_response
                },
                "finish_reason": "stop",
                "index": 0
            }]
        })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
