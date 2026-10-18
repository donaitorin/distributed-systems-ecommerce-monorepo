import check_not_found_csp as guard

POLICY = "default-src 'self'; script-src 'self' 'nonce-abc123' 'strict-dynamic'; style-src 'self' 'nonce-abc123'"


def test_a_page_whose_inline_elements_carry_the_nonce_is_accepted() -> None:
    html = '<style nonce="abc123">a{}</style><script nonce="abc123">1</script><script src="/x.js"></script>'

    assert guard.violations(html, POLICY) == []


def test_a_style_element_without_a_nonce_is_reported() -> None:
    assert guard.violations("<style>a{}</style>", POLICY) == ["<style> without the policy nonce"]


def test_a_script_with_another_nonce_is_reported() -> None:
    assert guard.violations('<script nonce="zzz">1</script>', POLICY) == [
        "<script> without the policy nonce"
    ]


def test_style_attributes_are_not_elements_and_are_ignored() -> None:
    assert guard.violations('<h1 style="margin:0">404</h1>', POLICY) == []


def test_a_missing_policy_or_nonce_is_reported() -> None:
    assert guard.violations("<p>x</p>", None) == ["the response has no Content-Security-Policy header"]
    assert guard.violations("<p>x</p>", "default-src 'self'") == [
        "the Content-Security-Policy has no nonce"
    ]
