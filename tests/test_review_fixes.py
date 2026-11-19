import pytest

from app import app, listing_media_is_representative, validate_maintenance_form


@pytest.mark.parametrize("contact,field", [
    ({"email": "not-email", "phone": ""}, "email"),
    ({"email": "", "phone": "x"}, "phone"),
])
def test_maintenance_rejects_unusable_contact(contact, field):
    _, errors = validate_maintenance_form({
        "resident_name": "Test Resident", "unit_reference": "B2",
        "description": "Leaking tap", "issue_category": "Plumbing",
        "priority": "Medium", **contact,
    })
    assert field in errors


@pytest.mark.parametrize("contact", [
    {"email": "resident@example.com", "phone": ""},
    {"email": "", "phone": "+234 801 234 5678"},
])
def test_maintenance_accepts_one_valid_contact(contact):
    _, errors = validate_maintenance_form({
        "resident_name": "Test Resident", "unit_reference": "B2",
        "description": "Leaking tap", "issue_category": "Plumbing",
        "priority": "Medium", **contact,
    })
    assert not errors


def test_media_disclosure_handles_mixed_and_supplied_galleries():
    supplied = {"image_path": "https://example.com/property.webp", "gallery_paths": []}
    assert not listing_media_is_representative(supplied)
    assert listing_media_is_representative({**supplied, "gallery_paths": ["images/building1.jpg"]})
    assert listing_media_is_representative({"image_path": "", "gallery_paths": [], "property_type": "House"})


def test_detail_discloses_seeded_representative_media():
    response = app.test_client().get("/properties/1")
    assert response.status_code == 200
    assert b"Representative media included" in response.data
    assert b"This gallery includes representative imagery" in response.data


@pytest.mark.parametrize("field,value", [("email", "not-email"), ("phone", "x")])
def test_invalid_contact_round_trip_keeps_input_and_links_error(monkeypatch, field, value):
    import app as app_module

    def reject_persistence(_):
        pytest.fail("Invalid contact must not create a maintenance ticket")

    monkeypatch.setattr(app_module, "create_maintenance_ticket_record", reject_persistence)
    client = app.test_client()
    with client.session_transaction() as session:
        session["_csrf_token"] = "review-contact-test"
    response = client.post("/tenant-services", data={
        "csrf_token": "review-contact-test", "resident_name": "Test Resident",
        "unit_reference": "Review B2", "description": "Leaking tap",
        "issue_category": "Plumbing", "priority": "Medium", field: value,
    })
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f'id="{field}-error"' in html
    assert f'aria-describedby="contact-help {field}-error"' in html
    assert f'value="{value}"' in html
    assert 'id="tenant-errors"' in html
