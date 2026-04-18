from app.models.economy import EconomicProfile

merchant = EconomicProfile(npc_id='goran', gold=50, goods={'iron_sword': 1})

print("=== ЦЕНА МЕЧА (база 15G) ===")
print(f"Знакомый (trust=0.8): {merchant.calculate_selling_price('iron_sword', 0.8)}G")
print(f"Незнакомец (trust=0.2): {merchant.calculate_selling_price('iron_sword', 0.2)}G")
print(f"Незнакомец+срочно: {merchant.calculate_selling_price('iron_sword', 0.2, 0.8)}G")

print("\n=== ИНФЛЯЦИЯ (Фаза 6 будет обновлять автоматически) ===")
print(f"Нормальная (1.003/год): {merchant.calculate_selling_price('iron_sword', 0.5, 0.0, 1.003)}G")
print(f"Кризис-неурожай (1.15/год): {merchant.calculate_selling_price('iron_sword', 0.5, 0.0, 1.15)}G")
print(f"Чумной год (1.30/год): {merchant.calculate_selling_price('iron_sword', 0.5, 0.0, 1.30)}G")

print("\n=== ЛОКАЛЬНЫЙ ДЕФИЦИТ (Фаза 3.1: LocationNode) ===")
print(f"Обычный город: {merchant.calculate_selling_price('food', 0.5, 0.0, 1.0, 1.0)}G")
print(f"Осаждённый (food ×2.0): {merchant.calculate_selling_price('food', 0.5, 0.0, 1.0, 2.0)}G")
print(f"Порт (iron_sword ×0.8): {merchant.calculate_selling_price('iron_sword', 0.5, 0.0, 1.0, 0.8)}G")

print('OK')