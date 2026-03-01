# Firebase TTS Function

This Cloud Function provides a secure TTS endpoint for mobile clients.

## Prereqs
- Firebase project created
- Text-to-Speech API enabled in the same Google Cloud project
- Firebase Auth enabled (anonymous is fine)

## Deploy
```bash
cd firebase_functions
npm install
firebase deploy --only functions:tts
```

## Client usage
Send a POST to the function URL with a Firebase ID token:

```http
POST https://<region>-<project>.cloudfunctions.net/tts
Authorization: Bearer <FIREBASE_ID_TOKEN>
Content-Type: application/json

{"text":"你好","voice":"yue-HK-Standard-A","rate":120}
```

Response:
```json
{"audioContent":"...base64...","timepoints":[{"markName":"s0","timeSeconds":0.0}]}
```
