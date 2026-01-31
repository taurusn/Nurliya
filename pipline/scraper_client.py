"""
HTTP client for the Google Maps Scraper Web API.
Handles job creation, status polling, and CSV download.
"""

import asyncio
import httpx
from typing import Optional
from config import SCRAPER_API_URL, SCRAPER_POLL_INTERVAL


class ScraperClient:
    """Async HTTP client for the Go scraper's Web API."""

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or SCRAPER_API_URL).rstrip("/")
        self.timeout = httpx.Timeout(30.0, read=60.0)

    async def create_job(
        self,
        query: str,
        depth: int = 10,
        lang: str = "en",
        email: bool = False,
        fast_mode: bool = False,
        max_time: int = 300,
        extra_reviews: bool = True,  # Enable extended reviews (~300 max)
    ) -> str:
        """
        Create a new scrape job.

        Args:
            query: Search query (e.g., "coffee shops in Riyadh")
            depth: Scroll depth for results (default 10)
            lang: Language code (default "en")
            email: Extract emails from websites
            fast_mode: Use fast mode with reduced data
            max_time: Maximum scrape time in seconds
            extra_reviews: Collect extended reviews up to ~300 (default True)

        Returns:
            Job ID from the scraper
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/jobs",
                json={
                    "name": query,
                    "keywords": [query],
                    "lang": lang,
                    "depth": depth,
                    "email": email,
                    "fast_mode": fast_mode,
                    "max_time": max_time,
                    "extra_reviews": extra_reviews,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["id"]

    async def get_job_status(self, job_id: str) -> dict:
        """
        Get the status of a scrape job.

        Returns:
            Dict with keys: id, name, date, status, data
            Status values: pending, working, ok, failed
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/api/v1/jobs/{job_id}")
            response.raise_for_status()
            return response.json()

    async def download_csv(self, job_id: str, output_path: str) -> str:
        """
        Download the CSV results for a completed job.

        Args:
            job_id: The scraper job ID
            output_path: Path to save the CSV file

        Returns:
            Path to the saved CSV file
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/jobs/{job_id}/download"
            )
            response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(response.content)

            return output_path

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: int = None,
        timeout: int = 600,
    ) -> dict:
        """
        Poll until job completes or fails.

        Args:
            job_id: The scraper job ID
            poll_interval: Seconds between status checks
            timeout: Maximum wait time in seconds

        Returns:
            Final job status dict

        Raises:
            TimeoutError: If job doesn't complete within timeout
            RuntimeError: If job fails
        """
        poll_interval = poll_interval or SCRAPER_POLL_INTERVAL
        elapsed = 0

        while elapsed < timeout:
            status = await self.get_job_status(job_id)
            # Note: Go scraper returns "Status" with capital S
            job_status = status.get("Status") or status.get("status", "unknown")

            if job_status == "ok":
                return status
            elif job_status == "failed":
                raise RuntimeError(f"Scraper job failed: {status}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Scraper job {job_id} timed out after {timeout}s")

    async def health_check(self) -> bool:
        """Check if the scraper API is reachable."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(f"{self.base_url}/")
                return response.status_code == 200
        except Exception:
            return False


# Sync wrapper for non-async contexts
class ScraperClientSync:
    """Synchronous wrapper for ScraperClient."""

    def __init__(self, base_url: str = None):
        self.async_client = ScraperClient(base_url)

    def create_job(self, query: str, **kwargs) -> str:
        return asyncio.run(self.async_client.create_job(query, **kwargs))

    def get_job_status(self, job_id: str) -> dict:
        return asyncio.run(self.async_client.get_job_status(job_id))

    def download_csv(self, job_id: str, output_path: str) -> str:
        return asyncio.run(self.async_client.download_csv(job_id, output_path))

    def wait_for_completion(self, job_id: str, **kwargs) -> dict:
        return asyncio.run(self.async_client.wait_for_completion(job_id, **kwargs))

    def health_check(self) -> bool:
        return asyncio.run(self.async_client.health_check())


if __name__ == "__main__":
    # Test the client
    import sys

    client = ScraperClientSync()

    if client.health_check():
        print(f"Scraper API is reachable at {SCRAPER_API_URL}")
    else:
        print(f"Scraper API is NOT reachable at {SCRAPER_API_URL}")
        sys.exit(1)
