from scraper import tech_detector


def test_detect_shopify():
    html = '<script src="https://cdn.shopify.com/s/files/theme.js"></script>'
    result = tech_detector.detect_ecommerce_platform(html)
    assert result["is_shopify"] is True
    assert result["is_woocommerce"] is False


def test_detect_woocommerce():
    html = '<body class="woocommerce woocommerce-page">'
    result = tech_detector.detect_ecommerce_platform(html)
    assert result["is_woocommerce"] is True
    assert result["is_shopify"] is False


def test_detect_other_ecommerce():
    html = '<script src="https://cdn11.bigcommerce.com/assets/app.js"></script>'
    result = tech_detector.detect_ecommerce_platform(html)
    assert result["other_platform"] == "BigCommerce"


def test_detect_meta_pixel():
    html = "<script>fbq('init', '123456');</script>"
    assert tech_detector.detect_meta_pixel(html) is True


def test_detect_google_analytics():
    html = '<script src="https://www.googletagmanager.com/gtag/js?id=G-ABC123"></script>'
    assert tech_detector.detect_google_analytics(html) is True


def test_detect_live_chat_intercom():
    html = '<script src="https://widget.intercom.io/widget/abc"></script>'
    assert tech_detector.detect_live_chat(html) == "Intercom"


def test_detect_no_live_chat():
    html = "<html><body>Just a plain page</body></html>"
    assert tech_detector.detect_live_chat(html) == ""


def test_detect_whatsapp_widget():
    html = '<a href="https://wa.me/15551234567">Chat</a>'
    assert tech_detector.detect_whatsapp_widget(html) is True
