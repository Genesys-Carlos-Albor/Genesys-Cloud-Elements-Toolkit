from gctoolkit.reports import load_all, trunks

from test_core import FakeResponse, make_client


def prop(instance=None, default=None, **extra):
    value = {"default": default, **({"instance": instance} if instance is not None else {})}
    return {"type": None, "value": value, **extra}


def test_properties_go_to_their_domain_sheet():
    assert trunks.property_domain("trunk_media_codec") == "Media"
    assert trunks.property_domain("trunk_outboundIdentity_callingName") == "Outbound Identity"
    assert trunks.property_domain("trunk_outbound_tgrp") == "Outbound Identity"
    assert trunks.property_domain("trunk_protocol") == "Protocol"
    assert trunks.property_domain("trunk_sip_uuiPd") == "Protocol"
    assert trunks.property_domain("trunk_recording_enabled") == "Recording"
    assert trunks.property_domain("trunk_transport_tls_ciphers") == "Transport"
    assert trunks.property_domain("trunk_provisioning_httpPort") == "Provisioning"
    assert trunks.property_domain("trunk_maxDialTimeout") == "Trunk Base Settings"
    assert trunks.property_domain("trunk_consult_recording_enabled") == "Trunk Base Settings"


def test_property_value_prefers_instance_and_masks_secrets():
    assert trunks.property_value(prop(instance="5m", default="10m"), "trunk_maxDialTimeout") == "5m"
    assert trunks.property_value(prop(default="SIP"), "trunk_protocol") == "SIP"
    assert trunks.property_value(prop(instance=False, default=True), "trunk_enabled") is False
    assert trunks.property_value(prop(instance=["Source", "Site"]), "trunk_calling_id_priority") == "Source\nSite"
    assert trunks.property_value(prop(instance=[]), "trunk_access_acl_allowList") == "Empty"
    assert trunks.property_value(prop(instance="00"), "trunk_sip_uuiPd") == "00"
    assert trunks.property_value(prop(instance="s3cret"), "trunk_sip_authorization_credentials_password") == "********"
    assert trunks.property_value(prop(default=""), "trunk_sip_authorization_credentials_password") == "Empty"
    assert trunks.property_value(None, "trunk_media_codec") == "Empty"


def test_unique_by_id_keeps_first_in_order():
    items = [{"id": "a", "n": 1}, {"id": "b"}, {"id": "a", "n": 2}, {"id": "c"}]
    assert trunks.unique_by_id(items) == [{"id": "a", "n": 1}, {"id": "b"}, {"id": "c"}]


def test_get_trunks_builds_one_sheet_per_domain():
    base = {
        "id": "tb1", "name": "BYOC Carrier", "trunkType": "EXTERNAL", "modifiedBy": "u1",
        "dateModified": "2025-11-19T15:04:05.123Z",
        "properties": {
            "trunk_maxDialTimeout": prop(instance="5m"),
            "trunk_media_codec": prop(instance=["audio/opus", "audio/PCMU"]),
            "trunk_sip_authorization_credentials_password": prop(default="hunter2"),
        },
    }
    trunk = {"id": "t1", "name": "Carrier A", "trunkBase": {"id": "tb1", "name": "BYOC Carrier"},
             "ipStatus": {"address": "10.0.0.1"}, "optionsStatus": [], "proxyAddressList": ["1.2.3.4:5061"]}
    client = make_client({
        "/api/v2/users": [FakeResponse(body={"entities": [{"id": "u1", "name": "Ana Admin"}], "pageCount": 1})],
        "/api/v2/telephony/providers/edges/trunks": [FakeResponse(body={"entities": [trunk, trunk], "pageCount": 1})],
        "/api/v2/telephony/providers/edges/trunkbasesettings": [
            FakeResponse(body={"entities": [{"id": "tb1", "name": "BYOC Carrier"}], "pageCount": 1}),
        ],
        "/api/v2/telephony/providers/edges/trunkbasesettings/tb1": [FakeResponse(body=base)],
    })

    result = load_all()["get-trunks"].run(client, lambda _: None)

    (row,) = result.rows
    assert (row["ipStatus"], row["optionsStatus"], row["proxyAddressList"]) == ("10.0.0.1", "Empty", "1.2.3.4:5061")
    sheets = {s.name: s.rows for s in result.extra_sheets}
    assert list(sheets) == ["Trunk Base Settings", "Media", "Outbound Identity", "Protocol", "Recording", "Transport", "Provisioning"]
    general = sheets["Trunk Base Settings"][0]
    assert (general["modifiedByName"], general["dateModified"], general["timeModified"]) == ("Ana Admin", "2025-11-19", "15:04:05")
    assert general["trunk_maxDialTimeout"] == "5m"
    assert sheets["Media"][0] == {"trunkBaseName": "BYOC Carrier", "trunkBaseId": "tb1", "trunkType": "EXTERNAL",
                                  "trunk_media_codec": "audio/opus\naudio/PCMU"}
    assert sheets["Protocol"][0]["trunk_sip_authorization_credentials_password"] == "********"
