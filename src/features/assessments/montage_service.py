import httpx

from django.conf import settings


class RAGClient:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _create_client(self) -> httpx.AsyncClient:
        self._client = httpx.AsyncClient(
            base_url=settings.RAG_SERVICE_URL,
            headers={
                "Authorization": f"Bearer {settings.RAG_SERVICE_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30.0),
        )

        return self._client

    async def get_client(self) -> httpx.AsyncClient:
        """
        Retorna o cliente atual.

        Caso não exista ou esteja fechado,
        cria uma nova conexão.
        """

        if self._client is None or self._client.is_closed:
            await self._create_client()

        return self._client

    async def close(self):
        """
        Fecha explicitamente o cliente HTTP.
        """

        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

        self._client = None

    async def reset(self):
        """
        Mata a conexão atual e cria uma nova.
        """

        await self.close()
        await self._create_client()

    async def send_request(
        self,
        method: str,
        url: str,
        *,
        retry: bool = True,
        **kwargs,
    ) -> dict:
        client = await self.get_client()

        try:
            response = await client.request(
                method=method,
                url=url,
                **kwargs,
            )

            response.raise_for_status()

            return response.json()

        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadError,
            httpx.RemoteProtocolError,
        ):
            if not retry:
                raise

            # A conexão pode ter morrido.
            # Mata o cliente inteiro e cria outro.
            await self.reset()

            return await self.send_request(
                method,
                url,
                retry=False,
                **kwargs,
            )

    async def __aenter__(self):
        await self.get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
        
        
        
class AssessmentAssemblyRAGService(BaseRAGService):

    async def create_assessment(
        self,
        *,
        subject: str,
        topic: str,
        difficulty: str,
        question_count: int,
        restrictions: list[str] | None = None,
    ) -> dict:

        payload = {
            "subject": subject,
            "topic": topic,
            "difficulty": difficulty,
            "question_count": question_count,
            "restrictions": restrictions or [],
        }

        return await self.client.send_request(
            method="POST",
            url="/rag/assessment/assemble",
            json=payload,
        )
        
        
        
class QuestionGenerationRAGService(BaseRAGService):

    async def create_question(
        self,
        *,
        subject: str,
        topic: str,
        question_type: str,
        difficulty: str,
        prompt: str | None = None,
        restrictions: list[str] | None = None,
    ) -> dict:

        payload = {
            "subject": subject,
            "topic": topic,
            "question_type": question_type,
            "difficulty": difficulty,
            "prompt": prompt,
            "restrictions": restrictions or [],
        }

        return await self.client.send_request(
            method="POST",
            url="/rag/questions/generate",
            json=payload,
        )