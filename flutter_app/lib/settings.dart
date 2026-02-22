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
