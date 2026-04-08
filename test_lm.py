from openai import OpenAI
client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
try:
    response = client.chat.completions.create(
        model="local-model",
        messages=[
           {"role": "system", "content": "You are a JSON assistant. Output JSON."},
           {"role": "user", "content": "hello"}
        ],
        response_format={"type": "json_object"}
    )
    print("SUCCESS:", response.choices[0].message.content)
except Exception as e:
    print(f"ERROR: {e}")
