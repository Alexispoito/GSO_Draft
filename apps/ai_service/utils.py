# apps/ai_service/utils.py
import os
from openai import OpenAI

# -------------------------------
# OpenRouter / DeepSeek LLM Setup
# -------------------------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable not set")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

MODEL_NAME = "deepseek/deepseek-r1-distill-llama-8b"


# -------------------------------
# AI Query Function
# -------------------------------
def query_openrouter(prompt: str) -> str:
    """
    Generic call to OpenRouter API (DeepSeek-R1 Distill Llama 8B).
    """
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Error generating AI content: {e}"


# -------------------------------
# WAR Description Generator
# -------------------------------
def generate_war_description(activity_name: str, unit: str = None, personnel_names: list = None) -> str:
    """
    Generate a professional description for a Work Accomplishment Report (WAR)
    using the OpenRouter DeepSeek model.
    """
    prompt = (
        f"Write a concise, factual sentence describing the completed task: '{activity_name}'. "
        "Do not write job postings or generic skill descriptions. Only describe the actual work done. "
    )
    if unit:
        prompt += f" This was performed for the '{unit}' unit."
    if personnel_names:
        prompt += f" Personnel involved: {', '.join(personnel_names)}."
    prompt += " Only describe what was done, Keep it to one short sentence."

    return query_openrouter(prompt)


# -------------------------------
# IPMT Summary Generator
# -------------------------------
def generate_ipmt_summary(success_indicator: str, war_descriptions: list) -> str:
    """
    Generate an accomplishment statement for a given Success Indicator
    based on multiple Work Accomplishment Reports (WARs).
    """
    if not war_descriptions:
        return f"No accomplishments recorded for indicator: {success_indicator}."

    activities_text = "\n".join([f"- {desc}" for desc in war_descriptions])
    prompt = (
        f"Summarize the following accomplishments for the success indicator '{success_indicator}':\n\n"
        f"{activities_text}\n\n"
        "Write in a clear, concise, factual way. Focus on what was achieved, not generic skills."
    )

    return query_openrouter(prompt)
