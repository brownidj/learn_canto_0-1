import 'dart:io' show Platform;

String googleTtsApiKey() {
  const buildTime = String.fromEnvironment('GOOGLE_TTS_API_KEY');
  if (buildTime.isNotEmpty) {
    return buildTime;
  }
  return Platform.environment['GOOGLE_TTS_API_KEY'] ?? '';
}

String googleTtsProxyUrl() {
  const buildTime = String.fromEnvironment('GOOGLE_TTS_PROXY_URL');
  if (buildTime.isNotEmpty) {
    return buildTime;
  }
  return Platform.environment['GOOGLE_TTS_PROXY_URL'] ?? '';
}

String firebaseTtsUrl() {
  const buildTime = String.fromEnvironment('FIREBASE_TTS_URL');
  if (buildTime.isNotEmpty) {
    return buildTime;
  }
  final env = Platform.environment['FIREBASE_TTS_URL'];
  if (env != null && env.isNotEmpty) {
    return env;
  }
  return 'https://us-central1-learncanto-ebbc0.cloudfunctions.net/tts';
}
