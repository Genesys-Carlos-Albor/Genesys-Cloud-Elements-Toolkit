"""Genesys Cloud Platform API client: client-credentials login, paging and rate-limit retries."""

import threading
import time

import requests

from .profiles import Profile


class ApiError(Exception):
    def __init__(self, method: str, path: str, response: requests.Response):
        self.status = response.status_code
        self.correlation_id = response.headers.get("ININ-Correlation-Id")
        try:
            message = response.json().get("message")
        except ValueError:
            message = response.text[:300]
        super().__init__(f"{method} {path} failed with HTTP {self.status}: {message} (correlation id {self.correlation_id})")


class GenesysClient:
    def __init__(self, profile: Profile, session: requests.Session | None = None, max_retries: int = 5, timeout: int = 60):
        self.profile = profile
        self.api_base = f"https://api.{profile.environment}"
        self.token_url = f"https://login.{profile.environment}/oauth/token"
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires = 0.0
        self._token_lock = threading.Lock()

    def _access_token(self, force: bool = False) -> str:
        with self._token_lock:
            if force or not self._token or time.time() > self._token_expires - 60:
                resp = self.session.post(
                    self.token_url,
                    data={"grant_type": "client_credentials"},
                    auth=(self.profile.client_id, self.profile.client_secret),
                    timeout=self.timeout,
                )
                if resp.status_code != 200:
                    raise ApiError("POST", "/oauth/token", resp)
                body = resp.json()
                self._token = body["access_token"]
                self._token_expires = time.time() + body.get("expires_in", 3600)
            return self._token

    def request(self, method: str, path: str, params: dict | None = None, json: dict | list | None = None):
        url = path if path.startswith("http") else self.api_base + path
        refreshed = False
        for attempt in range(self.max_retries + 1):
            headers = {"Authorization": f"Bearer {self._access_token()}"}
            resp = self.session.request(method, url, params=params, json=json, headers=headers, timeout=self.timeout)
            if resp.status_code == 401 and not refreshed:
                self._access_token(force=True)
                refreshed = True
                continue
            if (resp.status_code == 429 or resp.status_code >= 500) and attempt < self.max_retries:
                retry_after = resp.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else min(2 ** attempt, 30))
                continue
            if not resp.ok:
                raise ApiError(method, path, resp)
            return resp.json() if resp.content else None
        raise ApiError(method, path, resp)

    def get(self, path: str, **params):
        return self.request("GET", path, params=params or None)

    def download(self, url: str, path, attempts: int = 3) -> None:
        """Save a pre-signed download URL to `path`. No bearer token is sent; the URL carries its own signature."""
        for attempt in range(1, attempts + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                path.write_bytes(resp.content)
                return
            except requests.RequestException:
                if attempt == attempts:
                    raise
                time.sleep(2 * attempt)

    def get_all(self, path: str, page_size: int = 100, **params) -> list[dict]:
        """Collect 'entities' across every page, following nextUri (cursor paging) or pageNumber/pageCount."""
        entities: list[dict] = []
        page = 1
        data = self.get(path, pageSize=page_size, pageNumber=page, **params) or {}
        seen_next: set[str] = set()
        while True:
            batch = data.get("entities") or []
            entities.extend(batch)
            next_uri = data.get("nextUri")
            page_count = data.get("pageCount")
            if not batch:
                return entities
            if next_uri and next_uri not in seen_next:
                seen_next.add(next_uri)
                data = self.get(next_uri) or {}
            elif not next_uri and page_count is not None and page < page_count:
                page += 1
                data = self.get(path, pageSize=page_size, pageNumber=page, **params) or {}
            else:
                return entities
