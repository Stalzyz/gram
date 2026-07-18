from scraper import contact_extractor

SAMPLE_HTML = """
<html><body>
  <footer>
    <a href="mailto:hello@example-store.com">Email us</a>
    <a href="tel:+14155552671">Call</a>
    <a href="https://wa.me/14155552671">Chat on WhatsApp</a>
    <a href="https://facebook.com/examplestore">Facebook</a>
    <address>123 Main St, Springfield, USA</address>
  </footer>
</body></html>
"""


def test_extract_emails_from_mailto():
    emails = contact_extractor.extract_emails(SAMPLE_HTML)
    assert "hello@example-store.com" in emails


def test_extract_phone_numbers_from_tel_link():
    phones = contact_extractor.extract_phone_numbers(SAMPLE_HTML)
    assert any("415" in p or "4155552671" in p.replace(" ", "").replace("-", "") for p in phones)


def test_extract_whatsapp_number():
    numbers = contact_extractor.extract_whatsapp_numbers(SAMPLE_HTML)
    assert "+14155552671" in numbers


def test_extract_address():
    address = contact_extractor.extract_address(SAMPLE_HTML)
    assert "Springfield" in address


def test_extract_facebook_page():
    fb = contact_extractor.extract_facebook_page(SAMPLE_HTML)
    assert "facebook.com/examplestore" in fb


def test_junk_email_filtered_out():
    html = '<a href="mailto:noreply@sentry.io">x</a><a href="mailto:real@shop.com">y</a>'
    emails = contact_extractor.extract_emails(html)
    assert "noreply@sentry.io" not in emails
    assert "real@shop.com" in emails
