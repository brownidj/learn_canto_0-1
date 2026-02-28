import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

class MainTtsService {
  final FlutterTts _tts = FlutterTts();
  bool _initialized = false;

  Future<void> _init() async {
    if (_initialized) {
      return;
    }
    _initialized = true;
    await _tts.awaitSpeakCompletion(true);
    if (Platform.isIOS) {
      await _tts.setSharedInstance(true);
      await _tts.setIosAudioCategory(
        IosTextToSpeechAudioCategory.playback,
        [
          IosTextToSpeechAudioCategoryOptions.mixWithOthers,
          IosTextToSpeechAudioCategoryOptions.defaultToSpeaker,
        ],
      );
    }
    _tts.setErrorHandler((msg) {
      debugPrint('TTS: flutter_tts error=$msg');
    });
    _tts.setStartHandler(() {
      debugPrint('TTS: flutter_tts start');
    });
    _tts.setCompletionHandler(() {
      debugPrint('TTS: flutter_tts complete');
    });
  }

  Future<List<Map<String, String>>> listVoices() async {
    await _init();
    try {
      final voices = await _tts.getVoices;
      if (voices is List) {
        return voices.map<Map<String, String>>((v) {
          if (v is Map) {
            return v.map((k, val) => MapEntry(k.toString(), val.toString()));
          }
          return <String, String>{};
        }).where((v) => v.isNotEmpty).toList();
      }
    } catch (_) {}
    return [];
  }

  Future<void> stop() async {
    await _tts.stop();
  }

  Future<void> speak(
    String text, {
    double? rate,
    String? voiceName,
    String? locale,
  }) async {
    await _init();
    debugPrint('TTS: flutter_tts speak len=${text.length} rate=$rate voice=$voiceName locale=$locale');
    if (locale != null && locale.isNotEmpty) {
      await _tts.setLanguage(locale);
    }
    if (voiceName != null && voiceName.isNotEmpty) {
      await _tts.setVoice({'name': voiceName, 'locale': locale ?? ''});
    }
    if (rate != null) {
      await _tts.setSpeechRate(rate);
    }
    await _tts.speak(text);
  }

  Future<void> speakAndWait(
    String text, {
    double? rate,
    String? voiceName,
    String? locale,
  }) async {
    await _init();
    debugPrint('TTS: flutter_tts speakAndWait len=${text.length} rate=$rate voice=$voiceName locale=$locale');
    if (locale != null && locale.isNotEmpty) {
      await _tts.setLanguage(locale);
    }
    if (voiceName != null && voiceName.isNotEmpty) {
      await _tts.setVoice({'name': voiceName, 'locale': locale ?? ''});
    }
    if (rate != null) {
      await _tts.setSpeechRate(rate);
    }
    final completer = Completer<void>();
    _tts.setCompletionHandler(() {
      if (!completer.isCompleted) {
        completer.complete();
      }
    });
    _tts.setErrorHandler((_) {
      if (!completer.isCompleted) {
        completer.complete();
      }
    });
    await _tts.speak(text);
    await completer.future;
  }
}
