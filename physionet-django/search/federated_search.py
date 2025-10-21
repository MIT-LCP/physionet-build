from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
import logging

from .models import FederatedSite
from .adapters import get_adapter

logger = logging.getLogger(__name__)


class FederatedSearchService:
    """Orchestrates federated search across multiple sites"""

    @staticmethod
    def is_enabled() -> bool:
        """Check if federated search is enabled (has active sites)"""
        return FederatedSite.objects.filter(enabled=True).exists()

    @staticmethod
    def search(search_term: str, resource_type: List[str] = None,
               page: int = 1, page_size: int = 10) -> List[Dict]:
        """
        Execute federated search across all enabled sites.

        Returns list of normalized results in order:
        - Results from sites in order of completion
        """
        if not FederatedSearchService.is_enabled():
            return []

        # Get all enabled sites
        sites = FederatedSite.objects.filter(enabled=True).order_by('order', 'name')

        if not sites.exists():
            return []

        all_results = []

        # Execute searches in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all search tasks
            future_to_site = {
                executor.submit(
                    FederatedSearchService._search_single_site,
                    site, search_term, resource_type, page, page_size
                ): site
                for site in sites
            }

            # Collect results as they complete (maintains order of completion)
            for future in as_completed(future_to_site):
                site = future_to_site[future]
                try:
                    site_results = future.result()
                    if site_results:
                        # Append results in order of completion
                        all_results.extend(site_results)
                        logger.info(f"Received {len(site_results)} results from {site.name}")
                except Exception as e:
                    # Silent failure - just log
                    logger.error(f"Failed to get results from {site.name}: {str(e)}")

        return all_results

    @staticmethod
    def _search_single_site(site: FederatedSite, search_term: str,
                            resource_type: List[str], page: int,
                            page_size: int) -> List[Dict]:
        """Execute search on a single site"""
        try:
            adapter = get_adapter(site)
            result = adapter.search(search_term, resource_type, page, page_size)

            if result['success']:
                return result['results']
            else:
                logger.warning(f"Search failed for {site.name}: {result.get('error')}")
                return []
        except Exception as e:
            logger.error(f"Exception searching {site.name}: {str(e)}")
            return []
