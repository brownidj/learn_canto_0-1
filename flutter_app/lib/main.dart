import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'ui/screens/add/add_screen.dart';
import 'ui/screens/edit/edit_screen.dart';
import 'ui/screens/launch/launch_screen.dart';
import 'ui/screens/main/main_screen.dart';

void main() {
  runApp(const LearnCantoApp());
}

class LearnCantoApp extends StatelessWidget {
  const LearnCantoApp({super.key});

  @override
  Widget build(BuildContext context) {
    const baseBackground = Color(0xFFDCE8F6);
    const panelBackground = Color(0xFFFDEEE6);
    const accent = Color(0xFFB2E0D4);
    const accentDark = Color(0xFF0C1B33);
    const buttonFill = Color(0xFFF5C2D3);
    const outline = Color(0xFFA3C1E0);
    final scheme = ColorScheme.fromSeed(
      seedColor: accent,
      brightness: Brightness.light,
    ).copyWith(
      primary: accent,
      onPrimary: accentDark,
      secondary: buttonFill,
      onSecondary: accentDark,
      background: baseBackground,
      onBackground: accentDark,
      surface: panelBackground,
      onSurface: accentDark,
      outline: outline,
      outlineVariant: accent,
    );
    return MaterialApp(
      title: 'LearnCanto',
      theme: ThemeData(
        colorScheme: scheme,
        scaffoldBackgroundColor: baseBackground,
        appBarTheme: const AppBarTheme(
          backgroundColor: baseBackground,
          foregroundColor: accentDark,
          elevation: 0,
        ),
        inputDecorationTheme: const InputDecorationTheme(
          filled: true,
          fillColor: panelBackground,
          border: OutlineInputBorder(
            borderSide: BorderSide(color: accent),
            borderRadius: BorderRadius.all(Radius.circular(6)),
          ),
          enabledBorder: OutlineInputBorder(
            borderSide: BorderSide(color: accent),
            borderRadius: BorderRadius.all(Radius.circular(6)),
          ),
          focusedBorder: OutlineInputBorder(
            borderSide: BorderSide(color: outline),
            borderRadius: BorderRadius.all(Radius.circular(6)),
          ),
          contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: buttonFill,
            foregroundColor: accentDark,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(6),
              side: const BorderSide(color: accent),
            ),
            textStyle: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            foregroundColor: accentDark,
            side: const BorderSide(color: accent),
          ),
        ),
      ),
      home: const _LaunchGate(),
    );
  }
}

class _LaunchGate extends StatefulWidget {
  const _LaunchGate();

  @override
  State<_LaunchGate> createState() => _LaunchGateState();
}

class _LaunchGateState extends State<_LaunchGate> {
  bool _started = false;

  @override
  Widget build(BuildContext context) {
    if (_started) {
      return const _OrientationHome();
    }
    return LaunchScreen(
      onStart: () {
        setState(() {
          _started = true;
        });
      },
    );
  }
}

enum _ScreenMode { main, add, edit }

class _OrientationHome extends StatefulWidget {
  const _OrientationHome();

  @override
  State<_OrientationHome> createState() => _OrientationHomeState();
}

class _OrientationHomeState extends State<_OrientationHome> {
  _ScreenMode _desired = _ScreenMode.main;
  Orientation? _lastOrientation;
  bool _awaitPortrait = false;
  bool _awaitLandscape = false;
  String? _overlayMessage;
  bool _addBuilt = false;
  bool _editBuilt = false;

  @override
  void initState() {
    super.initState();
    _requestFreeRotation();
  }

  Future<void> _setDesired(_ScreenMode mode) async {
    if (_desired == mode) {
      return;
    }
    setState(() {
      _desired = mode;
    });
  }

  Future<void> _requestPortrait({bool releaseAfter = false}) async {
    debugPrint('Orientation: request portrait releaseAfter=$releaseAfter');
    await SystemChrome.setPreferredOrientations(const [
      DeviceOrientation.portraitUp,
    ]);
    if (releaseAfter) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _requestFreeRotation();
      });
    }
  }

  Future<void> _requestLandscape({bool releaseAfter = false}) async {
    debugPrint('Orientation: request landscape releaseAfter=$releaseAfter');
    await SystemChrome.setPreferredOrientations(const [
      DeviceOrientation.landscapeLeft,
      DeviceOrientation.landscapeRight,
    ]);
    if (releaseAfter) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _requestFreeRotation();
      });
    }
  }

  Future<void> _requestFreeRotation() async {
    debugPrint('Orientation: request free rotation');
    await SystemChrome.setPreferredOrientations(DeviceOrientation.values);
  }

  void _handleOrientation(Orientation orientation) {
    debugPrint('Orientation: handle $orientation desired=$_desired awaitPortrait=$_awaitPortrait awaitLandscape=$_awaitLandscape');
    if (_awaitPortrait) {
      if (orientation == Orientation.portrait) {
        _awaitPortrait = false;
        _overlayMessage = null;
        _setDesired(_ScreenMode.edit);
        _requestFreeRotation();
      }
      return;
    }
    if (_awaitLandscape) {
      if (orientation == Orientation.landscape) {
        _awaitLandscape = false;
        _overlayMessage = null;
        _setDesired(_ScreenMode.add);
        _requestFreeRotation();
      }
      return;
    }
    switch (_desired) {
      case _ScreenMode.main:
        if (orientation == Orientation.landscape) {
          _setDesired(_ScreenMode.add);
        }
        break;
      case _ScreenMode.add:
        if (orientation == Orientation.portrait) {
          _setDesired(_ScreenMode.main);
        }
        break;
      case _ScreenMode.edit:
        if (orientation == Orientation.landscape) {
          _setDesired(_ScreenMode.add);
        }
        break;
    }
  }

  int _indexFor(Orientation orientation) {
    if (orientation == Orientation.landscape) {
      if (_desired == _ScreenMode.edit) {
        return 1; // add
      }
      return 1; // add
    }
    // portrait
    if (_desired == _ScreenMode.add) {
      return 0; // main
    }
    if (_desired == _ScreenMode.edit) {
      return 2; // edit
    }
    return 0; // main
  }

  @override
  Widget build(BuildContext context) {
    return OrientationBuilder(
      builder: (context, orientation) {
        debugPrint('Orientation: $orientation desired=$_desired');
        if (_lastOrientation != orientation) {
          _lastOrientation = orientation;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            _handleOrientation(orientation);
          });
        }
        final index = _indexFor(orientation);
        if (index == 1 && !_addBuilt) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            setState(() {
              _addBuilt = true;
            });
          });
        }
        if (index == 2 && !_editBuilt) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            setState(() {
              _editBuilt = true;
            });
          });
        }
        debugPrint('Orientation: render index=$index desired=$_desired overlay=${_overlayMessage != null}');
        final content = IndexedStack(
          index: index,
          children: [
            const MainScreen(),
            _addBuilt
                ? AddScreen(
                    onRequestEdit: () async {
                      setState(() {
                        _overlayMessage = 'Rotate to portrait to edit.';
                      });
                      _awaitPortrait = true;
                      await _requestPortrait();
                    },
                  )
                : const SizedBox.shrink(),
            _editBuilt
                ? EditScreen(
                    onRequestClose: () async {
                      setState(() {
                        _overlayMessage = 'Rotate to landscape to return to Add.';
                      });
                      _awaitLandscape = true;
                      await _requestLandscape();
                    },
                  )
                : const SizedBox.shrink(),
          ],
        );
        if (_overlayMessage == null) {
          return content;
        }
        return Stack(
          children: [
            content,
            Positioned.fill(
              child: Container(
                color: Colors.black.withOpacity(0.35),
                alignment: Alignment.center,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.black12),
                  ),
                  child: Text(
                    _overlayMessage ?? '',
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}
