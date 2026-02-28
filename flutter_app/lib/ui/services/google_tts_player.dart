import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

class GooglePlaybackHandle {
  final DateTime startedAt;
  final Future<void> completed;

  GooglePlaybackHandle(this.startedAt, this.completed);
}

class GoogleTtsPlayer {
  final AudioPlayer _player = AudioPlayer();
  bool _listenersAttached = false;

  Future<GooglePlaybackHandle> playBase64Mp3(String base64Audio) async {
    _attachListeners();
    final bytes = base64Decode(base64Audio);
    if (bytes.isEmpty) {
      throw StateError('Google TTS audio was empty');
    }
    final startCompleter = Completer<DateTime>();
    late final StreamSubscription<PlayerState> sub;
    sub = _player.onPlayerStateChanged.listen((state) {
      if (state == PlayerState.playing && !startCompleter.isCompleted) {
        startCompleter.complete(DateTime.now());
        sub.cancel();
      }
    });
    final data = Uint8List.fromList(bytes);
    await _player.setReleaseMode(ReleaseMode.stop);
    if (Platform.isIOS) {
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/tts_${DateTime.now().microsecondsSinceEpoch}.mp3');
      await file.writeAsBytes(data, flush: true);
      await _player.setSourceDeviceFile(file.path);
    } else {
      await _player.setSourceBytes(data);
    }
    await _player.resume();
    final startedAt = await startCompleter.future.timeout(
      const Duration(milliseconds: 250),
      onTimeout: () => DateTime.now(),
    );
    final completed = _player.onPlayerComplete.first;
    return GooglePlaybackHandle(startedAt, completed);
  }

  Future<void> stop() async {
    await _player.stop();
  }

  void _attachListeners() {
    if (_listenersAttached) {
      return;
    }
    _listenersAttached = true;
    _player.onPlayerStateChanged.listen((state) {
      debugPrint('TTS: player state=$state');
    });
    _player.onPlayerComplete.listen((_) {
      debugPrint('TTS: player complete');
    });
    _player.onLog.listen((msg) {
      debugPrint('TTS: player log=$msg');
    });
  }
}
