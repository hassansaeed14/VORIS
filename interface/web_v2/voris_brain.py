import os
import subprocess
import webbrowser
import urllib.parse
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class VorisBrain:
    def __init__(self):
        self.knowledge_dir = os.path.join(os.path.dirname(__file__), "knowledge")
        
        if not os.path.exists(self.knowledge_dir):
            os.makedirs(self.knowledge_dir)
            
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_KEY")
        
        self.ai_enabled = False
        if api_key:
            self.client = Groq(api_key=api_key)
            self.model = "llama-3.3-70b-versatile"
            self.ai_enabled = True

    def get_local_knowledge(self, query: str) -> str:
        combined_context = ""
        query_words = set(query.lower().split())
        
        if not os.path.exists(self.knowledge_dir):
            return ""
            
        for filename in os.listdir(self.knowledge_dir):
            if filename.endswith(".txt"):
                file_path = os.path.join(self.knowledge_dir, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if any(word in content.lower() for word in query_words):
                            combined_context += f"\n--- Source: {filename} ---\n{content}\n"
                except Exception as e:
                    print(f"[VORIS ERROR] Could not read file {filename}: {str(e)}")
                    
        return combined_context

    def generate_response(self, user_message: str) -> str:
        text = user_message.lower().strip()

        # ==========================================
        # 1. SYSTEM ACTION INTERCEPTOR (The Hands)
        # ==========================================
        if "youtube" in text:
            if "play" in text or "search" in text:
                parts = text.split("play") if "play" in text else text.split("search")
                query = parts[-1].replace("for", "").strip()
                if query:
                    encoded_query = urllib.parse.quote_plus(query)
                    webbrowser.open(f"https://www.youtube.com/results?search_query={encoded_query}")
                    return f"Opening YouTube and searching for: '{query}'"
            webbrowser.open("https://www.youtube.com")
            return "Opening the YouTube homepage."
            
        elif "open whatsapp" in text:
            subprocess.run(["cmd", "/c", "start", "whatsapp://"])
            return "Launching WhatsApp Desktop Application."
            
        elif text in ["open c drive", "open local disk c", "open c", "c drive"]:
            subprocess.run(["explorer", "C:\\"])
            return "Opening Local Disk C Drive."
            
        elif text in ["open d drive", "open local disk d", "open d", "d drive"]:
            if os.path.exists("D:\\"):
                subprocess.run(["explorer", "D:\\"])
                return "Opening Local Disk D Drive."
            return "Operation failed: No D Drive partition detected."

        # ==========================================
        # 2. GROQ AI ROUTER (The Brain)
        # ==========================================
        if not self.ai_enabled:
            return "Voris Core Error: No valid Groq API key found in your .env file."

        local_context = self.get_local_knowledge(user_message)
        
        master_prompt = f"""
        You are VORIS, a highly intelligent and helpful AI assistant.
        
        Context from local documents:
        {local_context if local_context else "No specific local files matched this query."}
        
        Instructions: Use the local documents context to answer the question if relevant. 
        If the local context doesn't contain the answer, use your global knowledge base to answer accurately.
        
        User Question: {user_message}
        VORIS Response:
        """
        
        try:
            chat_completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": master_prompt}],
                model=self.model,
                temperature=0.3,
            )
            return chat_completion.choices[0].message.content.strip()
        except Exception as e:
            return f"Voris Brain Error: Generation failed. Details: {str(e)}"

if __name__ == "__main__":
    brain = VorisBrain()
    print("--- VORIS SECURE GROQ BRAIN + AUTOMATION ACTIVE ---")