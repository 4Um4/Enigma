import asyncio
import json
import re
import urllib.request


async def main():
    base_url = "http://127.0.0.1:8080"
    
    test_inputs = [
        "пусть Торнин уйдёт к двери",
        "Торнин, отойди к стойке",
        "я подхожу к столу",
        "заставь Лусю принести эль"
    ]
    
    scene_context = {
        "location_id": "tavern_silver_wolf",
        "npc_positions": {
            "tavern_keeper_tornin": {"name": "Торнин"},
            "maid_lusya": {"name": "Луся"}
        }
    }

    system_prompt = """Ты — семантический парсер. Переведи ввод игрока в строгий JSON.
Допустимые action_types: ["MOVE", "OBSERVE", "INTERACT", "ATTACK", "THREATEN", "PERSUADE", "FLIRT", "STEAL", "GIVE", "UNCERTAIN"].
Извлеки:
- action_type: тип действия.
- actor_reference: КТО совершает действие. Если игрок говорит о себе ("я подойду") — "player". Если приказывает NPC ("Торнин, отойди" или "пусть Торнин уйдёт") — имя NPC (например, "Торнин").
- target_reference: к кому или к чему направлено действие (строка).
- target_zone: ["HEAD", "TORSO", "ARMS", "LEGS", "GROIN", "UNDEFINED"].
- physical_force, emotional_charge, social_pressure, commitment_level: числа от 0.0 до 1.0.
- semantic: объект с ключами aggression, fear, shame, confidence, desperation (0.0-1.0).
Если не уверен, установи action_type = "UNCERTAIN".
Верни ТОЛЬКО валидный JSON без markdown разметки."""

    for text in test_inputs:
        print(f"\n--- Input: '{text}' ---")
        user_prompt = f"Ввод: \"{text}\"\nКонтекст: {json.dumps(scene_context, ensure_ascii=False)}"
        
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1
        }
        
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url}/v1/chat/completions",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            # Обход прокси Throne
            proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler)
            
            with opener.open(req, timeout=15) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                content = resp_data["choices"][0]["message"]["content"]
                
                # Очистка от markdown разметки
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0)
                
                parsed = json.loads(content)
                print(f"✅ Parsed JSON: {json.dumps(parsed, ensure_ascii=False, indent=2)}")
                print(f"➡️ Extracted actor_reference: {parsed.get('actor_reference', 'MISSING')}")
        except Exception as e:
            print(f"❌ Raw Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())