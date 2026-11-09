"""Exercise HTTP serialization, rather than mocking the provider's _request."""

from unittest.mock import patch

import httpx
import pytest

from providers.linkedin_company import LinkedInCompanyProvider


@pytest.mark.parametrize("kind,parameter", [("share", "shares"), ("ugcPost", "ugcPosts")])
def test_company_metrics_preserve_restli_list_syntax_on_wire(kind, parameter):
    client_class = httpx.Client
    requests = []

    def handle(request):
        requests.append(request)
        query = request.url.query.decode("ascii")
        assert f"{parameter}=List(urn%3Ali%3A{kind}%3A456)" in query
        assert "%253A" not in query
        assert request.url.params["organizationalEntity"] == "urn:li:organization:123"
        assert request.headers["X-Restli-Protocol-Version"] == "2.0.0"
        return httpx.Response(200, json={"elements": [{"totalShareStatistics": {"impressionCount": 42}}]})

    transport = httpx.MockTransport(handle)
    with patch("providers.base.httpx.Client", side_effect=lambda **kwargs: client_class(transport=transport, **kwargs)):
        result = LinkedInCompanyProvider({"organization_id": "123"}).get_post_metrics(
            "test-token", f"urn:li:{kind}:456"
        )
    assert len(requests) == 1
    assert result.impressions == 42
