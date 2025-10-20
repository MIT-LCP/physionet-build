from abc import ABC, abstractmethod
import requests
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class BaseRepositoryAdapter(ABC):
    """Base adapter for different repository types"""

    def __init__(self, federated_site):
        self.site = federated_site

    @abstractmethod
    def search(self, search_term: str, resource_type: List[str],
               page: int = 1, page_size: int = 10) -> Dict:
        """
        Execute search and return normalized results
        Returns: {
            'success': bool,
            'results': List[Dict],
            'error': Optional[str]
        }
        """
        pass

    @abstractmethod
    def normalize_result(self, raw_result: Dict) -> Dict:
        """Normalize a single result to common format"""
        pass


class PhysioNetAdapter(BaseRepositoryAdapter):
    """Adapter for PhysioNet API instances"""

    def search(self, search_term: str, resource_type: List[str],
               page: int = 1, page_size: int = 10) -> Dict:
        """Search PhysioNet API"""
        try:
            url = self.site.get_full_search_url()

            # Build query parameters
            params = {
                'search_term': search_term,
                'page': page,
            }

            # Add resource type filter (convert to 'all' or specific types)
            if resource_type:
                params['resource_type'] = resource_type
            else:
                params['resource_type'] = ['all']

            # Setup headers
            headers = {}
            if self.site.auth_token:
                headers['Authorization'] = f'Bearer {self.site.auth_token}'

            # Make request
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.site.timeout_seconds,
                verify=True  # Always verify SSL
            )

            response.raise_for_status()
            data = response.json()

            # Extract results (handle both paginated and non-paginated responses)
            results = data.get('results', data) if isinstance(data, dict) else data

            # Normalize each result
            normalized_results = [
                self.normalize_result(result)
                for result in results[:page_size]
            ]

            return {
                'success': True,
                'results': normalized_results,
                'error': None
            }

        except requests.Timeout:
            logger.warning(f"Timeout querying {self.site.name}")
            return {'success': False, 'results': [], 'error': 'timeout'}
        except requests.RequestException as e:
            logger.error(f"Error querying {self.site.name}: {str(e)}")
            return {'success': False, 'results': [], 'error': str(e)}
        except Exception as e:
            logger.error(f"Unexpected error with {self.site.name}: {str(e)}")
            return {'success': False, 'results': [], 'error': str(e)}

    def normalize_result(self, raw_result: Dict) -> Dict:
        """Normalize PhysioNet API result to common format"""
        return {
            'title': raw_result.get('title', 'Untitled'),
            'slug': raw_result.get('slug', ''),
            'version': raw_result.get('version', ''),
            'abstract': raw_result.get('abstract', ''),
            'short_description': raw_result.get('short_description', ''),
            'publish_date': raw_result.get('publish_date', ''),
            'resource_type': raw_result.get('resource_type', 0),
            'access_policy': raw_result.get('access_policy', 0),
            'main_storage_size': raw_result.get('main_storage_size', 0),
            'compressed_storage_size': raw_result.get('compressed_storage_size', 0),
            'license': raw_result.get('license', {}),
            'dua': raw_result.get('dua', {}),
            'doi': raw_result.get('version_doi', raw_result.get('doi', '')),
            # Federated metadata
            'is_federated': True,
            'source_site_name': self.site.name,
            'source_site_display_name': self.site.display_name,
            'source_site_url': self.site.base_url,
            'external_url': f"{self.site.base_url.rstrip('/')}/content/{raw_result.get('slug', '')}/{raw_result.get('version', '')}/",
        }


class GenericAPIAdapter(BaseRepositoryAdapter):
    """Adapter for generic API repositories (future extensibility)"""

    def search(self, search_term: str, resource_type: List[str],
               page: int = 1, page_size: int = 10) -> Dict:
        """To be implemented for non-PhysioNet repositories"""
        return {'success': False, 'results': [], 'error': 'not_implemented'}

    def normalize_result(self, raw_result: Dict) -> Dict:
        """To be implemented for non-PhysioNet repositories"""
        return {}


# Adapter factory
def get_adapter(federated_site) -> BaseRepositoryAdapter:
    """Factory to create appropriate adapter"""
    adapters = {
        'physionet': PhysioNetAdapter,
        'generic_api': GenericAPIAdapter,
    }
    adapter_class = adapters.get(federated_site.site_type, PhysioNetAdapter)
    return adapter_class(federated_site)
