import { onRequest } from 'firebase-functions/v2/https';
import { initializeApp } from 'firebase-admin/app';
import { getAuth } from 'firebase-admin/auth';
import { GoogleAuth } from 'google-auth-library';
import fetch from 'node-fetch';

initializeApp();

const GOOGLE_SCOPE = ['https://www.googleapis.com/auth/cloud-platform'];

function buildSsml(text) {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  const chars = [...escaped];
  const parts = ['<speak>'];
  for (let i = 0; i < chars.length; i += 1) {
    parts.push(`<mark name='s${i}'/>${chars[i]}`);
  }
  parts.push('</speak>');
  return parts.join('');
}

function extractVoiceLabel(name) {
  if (!name || typeof name !== 'string') {
    return '';
  }
  const parts = name.split('-');
  return parts[parts.length - 1] || name;
}

async function verifyAuth(req) {
  const authHeader = req.get('Authorization') || '';
  const match = authHeader.match(/^Bearer\s+(.+)$/i);
  if (!match) {
    throw new Error('missing_auth');
  }
  const token = match[1];
  await getAuth().verifyIdToken(token);
}

export const tts = onRequest({
  region: 'us-central1',
  cors: true,
  timeoutSeconds: 30,
}, async (req, res) => {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'method_not_allowed' });
    return;
  }

  try {
    try {
      await verifyAuth(req);
    } catch (err) {
      res.status(401).json({ error: 'missing_auth' });
      return;
    }

    const { text, voice, rate } = req.body || {};
    if (!text || typeof text !== 'string') {
      res.status(400).json({ error: 'missing_text' });
      return;
    }

    const ssml = buildSsml(text);
    const auth = new GoogleAuth({ scopes: GOOGLE_SCOPE });
    const client = await auth.getClient();
    const accessToken = await client.getAccessToken();

    const payload = {
      input: { ssml },
      voice: {
        languageCode: 'yue-HK',
        name: voice || '',
      },
      audioConfig: {
        audioEncoding: 'MP3',
        speakingRate: Number.isFinite(rate) ? Math.max(0.25, Math.min(4.0, rate / 120)) : 1.0,
      },
      enableTimePointing: ['SSML_MARK'],
    };

    const resp = await fetch('https://texttospeech.googleapis.com/v1beta1/text:synthesize', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const msg = await resp.text();
      res.status(resp.status).json({ error: 'tts_failed', detail: msg });
      return;
    }

    const data = await resp.json();
    res.json({
      audioContent: data.audioContent || '',
      timepoints: data.timepoints || [],
    });
  } catch (err) {
    res.status(500).json({ error: 'server_error', detail: String(err) });
  }
});

export const voices = onRequest({
  region: 'us-central1',
  cors: true,
  timeoutSeconds: 30,
}, async (req, res) => {
  if (req.method !== 'GET') {
    res.status(405).json({ error: 'method_not_allowed' });
    return;
  }
  try {
    try {
      await verifyAuth(req);
    } catch (err) {
      res.status(401).json({ error: 'missing_auth' });
      return;
    }

    const auth = new GoogleAuth({ scopes: GOOGLE_SCOPE });
    const client = await auth.getClient();
    const accessToken = await client.getAccessToken();
    const resp = await fetch('https://texttospeech.googleapis.com/v1/voices?languageCode=yue-HK', {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${accessToken.token}`,
      },
    });
    if (!resp.ok) {
      const msg = await resp.text();
      res.status(resp.status).json({ error: 'voices_failed', detail: msg });
      return;
    }
    const data = await resp.json();
    const rawVoices = Array.isArray(data.voices) ? data.voices : [];
    const voices = rawVoices.map((v) => {
      const name = v.name || '';
      const locale = v.languageCodes?.[0] || 'yue-HK';
      const label = extractVoiceLabel(name);
      return { name, locale, label };
    }).filter((v) => v.name && v.locale);
    res.json({ voices });
  } catch (err) {
    res.status(500).json({ error: 'server_error', detail: String(err) });
  }
});
