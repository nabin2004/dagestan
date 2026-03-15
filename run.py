import json
from dotenv import load_dotenv
from dagestan import Dagestan


load_dotenv()

mem = Dagestan(provider="openai", db_path='./memory1.json')
# Load the conversation export
with open("anthropic/conversation_14.json", "r") as f:
    data = json.load(f)

# Extract just the messages
messages = []
for msg in data["chat_messages"]:
    messages.append({
        "role": msg["sender"],  # "human" or "assistant"
        "content": msg["text"],
        "timestamp": msg["created_at"]
    })

def chat_llm():
    messages = llm.invoke
    mem.ingest(messages[:-1])
    retrive = mem.retrieve
    return messages

mem.ingest(messages)

context = mem.retrieve("What does the user care about?")
print("CONTEXT: ", context)

report = mem.curate()
print(f"Contradictions found: {report.contradictions_found}")
print(f"Contracdiction: ", report)
strategy = mem.strategy()
print("Any strategy: ",strategy)
