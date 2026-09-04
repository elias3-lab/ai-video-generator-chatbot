"""
Base API client for provider integrations.
"""

import requests
from typing import Optional, Dict, Any
from utils.errors import APIError
from utils.logger import logger
from config import settings


class APIClient:
    """Base API client with common functionality."""

    def __init__(self, api_key: str, base_url: str, timeout: Optional[int] = None):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout or settings.request_timeout_seconds
        self.session = requests.Session()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                data=data,
                json=json,
                files=files,
                params=params,
                timeout=self.timeout,
            )
            logger.debug(f"{method} {url} -> {response.status_code}")
            if response.status_code >= 400:
                error_msg = f"API Error {response.status_code}: {response.text[:200]}"
                logger.error(error_msg)
                raise APIError(error_msg)
            return response
        except requests.Timeout as e:
            error_msg = f"Request timeout for {method} {endpoint}"
            logger.error(error_msg)
            raise APIError(error_msg) from e
        except requests.ConnectionError as e:
            error_msg = f"Connection error for {method} {endpoint}"
            logger.error(error_msg)
            raise APIError(error_msg) from e
        except requests.RequestException as e:
            error_msg = f"Request failed for {method} {endpoint}: {str(e)}"
            logger.error(error_msg)
            raise APIError(error_msg) from e

    def get(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        """Make GET request."""
        return self._make_request("GET", endpoint, headers=headers, params=params)

    def post(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        """Make POST request."""
        return self._make_request(
            "POST",
            endpoint,
            headers=headers,
            data=data,
            json=json,
            files=files,
            params=params,
        )

    def close(self):
        """Close session."""
        self.session.close()
