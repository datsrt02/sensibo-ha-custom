# Sensibo APK analysis and Home Assistant custom component

## APK summary

- File analyzed: `Sensibo.xapk`
- App package: `com.sensibo.app`
- App version: `3.8.1` / version code `6001`
- Main app technology: Flutter, with the Dart AOT snapshot in `config.armeabi_v7a.apk/lib/armeabi-v7a/libapp.so`
- Android wrapper/widget logic is in `com.sensibo.app.apk/classes.dex`

## API behavior found in the app

The app uses Sensibo cloud endpoints under `https://home.sensibo.com`.

Important paths found:

- `POST /api/v1/sessions` for account login. The app stores cookies with `CookieJar`/`SET-COOKIE`.
- `GET /api/v1/users/me`
- `GET /api/v2/users/me/pods`
- `GET /api/v2/pods/{pod_id}`
- `PATCH /api/v2/pods/{pod_id}/acStates/{property}`
- `GET/POST/DELETE /api/v2/users/me/apiKeys` related to API key management in the app UI.

The app also contains the `X-API-KEY` header string and an API key management screen, so the integration supports both account login and API key authentication.

AC state fields found:

- `on`
- `mode`
- `targetTemperature`
- `temperatureUnit`
- `fanLevel`
- `swing`
- `horizontalSwing`
- `light`

Device payload fields found:

- `id`
- `room`
- `productModel`
- `connectionStatus`
- `remoteCapabilities`
- `features`
- `measurements`

## Local/LAN control finding

No direct local LAN control API was found in the APK. The app contains ESP provisioning and setup logic such as BLE provisioning, `prov-session`, `prov-config`, Wi-Fi scan/config protobufs, and `ENABLE_DEVICE_STATION_MODE`, but no evidence of a local runtime control endpoint such as HTTP, MQTT, CoAP, mDNS, SSDP, WebSocket, or a LAN `/acStates` API.

This component is therefore implemented as cloud polling/control. If packet capture later proves that a Sensibo device accepts local AC commands, the component can add a separate local transport while keeping the same climate entity layer.

## HACS installation

Add this as a HACS custom repository:

- Repository: `https://github.com/datsrt02/sensibo-ha-custom`
- Category: `Integration`

Then download `Sensibo Custom` from HACS and restart Home Assistant.

## Manual installation

Copy `custom_components/sensibo_custom` into Home Assistant's `config/custom_components/` directory, restart Home Assistant, then add the integration from Settings > Devices & services > Add integration > Sensibo Custom.

Authentication options:

- Sensibo account email/password: the integration logs in through `/api/v1/sessions` and syncs all pods from `/api/v2/users/me/pods`.
- Sensibo API key: the integration sends both `apiKey` query parameter and `X-API-KEY` header.

Each Sensibo AC-capable pod is exposed as a Home Assistant `climate` entity.

## Changelog

- `0.1.2`: Round Home Assistant temperature values before sending them to Sensibo, because Sensibo's `targetTemperature` API requires an integer.
- `0.1.3`: Refresh each pod's detail endpoint on every poll so state changes made from the Sensibo app are reflected back in Home Assistant. Poll interval is now 30 seconds.
