"""
Файл: frontend/chronicle_editor/api.py
Назначение: клиент chronicle-эндпоинтов (поверх HttpClient; Закон 1.1 — только DTO).
Зависимости: frontend.api_client
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from api_client import BackendError, HttpClient


class ChronicleApi:
    _DEFAULT_BASE_URL = "http://127.0.0.1:8000"

    def __init__(self, http: Optional[HttpClient] = None) -> None:
        # Самодостаточность: editor_screen не угадывает internals core —
        # API строит транспорт сам (прецедент llama_cpp_server_url).
        self._http = http or HttpClient(self._DEFAULT_BASE_URL)

    def list_npcs(self) -> List[Dict[str, Any]]:
        try:
            data = self._http.get("/api/chronicle/npcs")
            return list(data.get("canonical", []))
        except BackendError:
            return []

    def list_roster(self, campaign: str) -> List[Dict[str, Any]]:
        """C0.5: полный ростер NPC со статусом хроники (canon/draft/none).
        Единственный источник списка — сервер (вшитый дубликат устранён).
        Пустой список при недоступном сервере — приложение покажет статус
        (прецедент list_npcs)."""
        try:
            data = self._http.get(f"/api/chronicle/roster/{campaign}")
            return list(data.get("roster", []))
        except BackendError:
            return []

    def get_draft(self, campaign: str, npc_id: str) -> Optional[Dict[str, Any]]:
        try:
            data = self._http.get(f"/api/chronicle/{campaign}/{npc_id}/draft")
            return data.get("document") if data.get("status") == "OK" else None
        except BackendError:
            return None

    def save_draft(self, campaign: str, npc_id: str, document: Dict[str, Any]) -> bool:
        try:
            self._http.put(f"/api/chronicle/{campaign}/{npc_id}/draft", document)
            return True
        except BackendError:
            return False

    def resolve_question(
        self,
        campaign: str,
        npc_id: str,
        question_id: str,
        selected_option: str,
        selected_value: Optional[str] = None,
    ) -> bool:
        """FR-3.1 (T-CCH-03): резолюция вопроса в draft (4-опции + свободный ввод
        через selected_value). Писатель — автор в UI (запрет 2)."""
        doc = self.get_draft(campaign, npc_id)
        if not doc:
            return False
        changed = False
        for e in doc.get("entries") or []:
            for q in e.get("open_questions") or []:
                if q.get("question_id") == question_id:
                    q["selected_option"] = selected_option
                    q["selected_value"] = selected_value
                    changed = True
        if not changed:
            return False
        return self.save_draft(campaign, npc_id, doc)

    def canonize(self, campaign: str, npc_id: str) -> Dict[str, Any]:
        """FR-10.1: «Принять как канон». 422 = блок «Save = Contract» (T-CCH-04)."""
        try:
            return self._http.post(f"/api/chronicle/{campaign}/{npc_id}/canonize", {"campaign_id": campaign})
        except BackendError as e:
            return {"status": "BLOCKED", "detail": str(e)}

    def decompose(self, campaign: str, npc_id: str, fragment_ord: int, fragment: str) -> Dict[str, Any]:
        try:
            return self._http.post(
                f"/api/chronicle/{campaign}/{npc_id}/decompose",
                {"campaign_id": campaign, "npc_id": npc_id, "fragment_ord": fragment_ord, "fragment": fragment},
            )
        except BackendError as e:
            return {"status": "NOT_DECOMPOSED", "error": str(e)}
