"""
hi.myrepo - SSRF Protection Tests

Tests for URL validation against server-side request forgery.
"""
import pytest

from app.security.ssrf import SSRFError, SSRFProtector


@pytest.fixture
def protector():
    return SSRFProtector()


class TestSSRFProtector:
    def test_allows_valid_https(self, protector):
        url = protector.validate_url("https://example.com/health")
        assert url == "https://example.com/health"

    def test_allows_valid_http(self, protector):
        url = protector.validate_url("http://example.com/health")
        assert url == "http://example.com/health"

    def test_blocks_ftp_scheme(self, protector):
        with pytest.raises(SSRFError, match="Scheme"):
            protector.validate_url("ftp://example.com/file")

    def test_blocks_file_scheme(self, protector):
        with pytest.raises(SSRFError, match="Scheme"):
            protector.validate_url("file:///etc/passwd")

    def test_blocks_javascript_scheme(self, protector):
        with pytest.raises(SSRFError, match="Scheme"):
            protector.validate_url("javascript:alert(1)")

    def test_blocks_localhost(self, protector):
        with pytest.raises(SSRFError, match="blocked"):
            protector.validate_url("http://localhost:8080/admin")

    def test_blocks_127_0_0_1(self, protector):
        with pytest.raises(SSRFError, match="blocked"):
            protector.validate_url("http://127.0.0.1/admin")

    def test_blocks_0_0_0_0(self, protector):
        with pytest.raises(SSRFError, match="blocked"):
            protector.validate_url("http://0.0.0.0/admin")

    def test_blocks_metadata_endpoint(self, protector):
        with pytest.raises(SSRFError, match="blocked"):
            protector.validate_url("http://169.254.169.254/latest/meta-data/")

    def test_blocks_gcp_metadata(self, protector):
        with pytest.raises(SSRFError, match="blocked"):
            protector.validate_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_blocks_alibaba_metadata(self, protector):
        with pytest.raises(SSRFError, match="blocked"):
            protector.validate_url("http://100.100.100.200/latest/meta-data/")

    def test_blocks_private_ip_10(self, protector):
        with pytest.raises(SSRFError):
            protector.validate_url("http://10.0.0.1/admin")

    def test_blocks_private_ip_172(self, protector):
        with pytest.raises(SSRFError):
            protector.validate_url("http://172.16.0.1/admin")

    def test_blocks_private_ip_192(self, protector):
        with pytest.raises(SSRFError):
            protector.validate_url("http://192.168.1.1/admin")

    def test_blocks_ipv6_loopback(self, protector):
        with pytest.raises(SSRFError):
            protector.validate_url("http://[::1]/admin")

    def test_blocks_ipv6_private(self, protector):
        with pytest.raises(SSRFError):
            protector.validate_url("http://[fc00::1]/admin")

    def test_blocks_empty_hostname(self, protector):
        with pytest.raises(SSRFError, match="hostname"):
            protector.validate_url("http:///admin")

    def test_blocks_invalid_format(self, protector):
        with pytest.raises(SSRFError):
            protector.validate_url("not-a-url")

    def test_blocks_subdomain_of_blocked(self, protector):
        # Subdomains of blocked hostnames should also be blocked
        with pytest.raises(SSRFError, match="blocked"):
            protector.validate_url("http://evil.localhost/steal")

    def test_blocks_instance_data(self, protector):
        with pytest.raises(SSRFError, match="blocked"):
            protector.validate_url("http://instance-data/latest/meta-data/")

    def test_sanitize_redirect_url_allows_valid(self, protector):
        url = protector.sanitize_redirect_url("https://example.com/callback")
        assert url == "https://example.com/callback"
