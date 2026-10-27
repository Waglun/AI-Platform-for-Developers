from abc import ABC, abstractmethod
from typing import Any


class CRMClient(ABC):
    """Интерфейс взаимодействия с CRM."""

    @abstractmethod
    def find_contact(self, phone: str):
        """Найти контакт по телефону."""
        raise NotImplementedError

    @abstractmethod
    def create_lead(self, data: dict[str, Any]):
        """Создать заявку или вернуть существующую по ключу операции."""
        raise NotImplementedError

    @abstractmethod
    def add_comment(self, lead_id: int, text: str):
        """Добавить комментарий к заявке."""
        raise NotImplementedError