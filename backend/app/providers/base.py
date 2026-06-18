from typing import Any, List, Dict

class BaseProvider:
    def __init__(self, credential: Any):
        self.credential = credential

    async def chat_completion(self, model: str, messages: List[Dict[str, str]], **kwargs) -> Any:
        raise NotImplementedError()

    async def embedding(self, model: str, input_data: Any, **kwargs) -> Any:
        raise NotImplementedError()
