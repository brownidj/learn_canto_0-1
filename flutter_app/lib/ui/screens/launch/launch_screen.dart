import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class LaunchScreen extends StatefulWidget {
  final VoidCallback onStart;

  const LaunchScreen({super.key, required this.onStart});

  @override
  State<LaunchScreen> createState() => _LaunchScreenState();
}

class _LaunchScreenState extends State<LaunchScreen> {
  @override
  void initState() {
    super.initState();
    SystemChrome.setPreferredOrientations(const [
      DeviceOrientation.portraitUp,
    ]);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        fit: StackFit.expand,
        children: [
          Image.asset(
            'assets/images/victoria_harbour.jpeg',
            fit: BoxFit.cover,
          ),
          Container(color: Colors.black.withOpacity(0.2)),
          Positioned(
            top: 50,
            left: 16,
            right: 16,
            child: Center(
              child: Container(
                constraints: const BoxConstraints(maxWidth: 320),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.9),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: 'Cantonese: Say it\n',
                        style: TextStyle(fontWeight: FontWeight.w800),
                      ),
                      TextSpan(
                        children: [
                          const TextSpan(text: '• helps you learn to '),
                          const TextSpan(text: 'recognise', style: TextStyle(fontWeight: FontWeight.w800)),
                          const TextSpan(text: ' and '),
                          const TextSpan(text: 'pronounce', style: TextStyle(fontWeight: FontWeight.w800)),
                          const TextSpan(text: ' Cantonese\n'),
                          const TextSpan(text: '• focuses on '),
                          const TextSpan(text: 'spoken', style: TextStyle(fontWeight: FontWeight.w800)),
                          const TextSpan(text: ' Cantonese\n'),
                          const TextSpan(
                            text:
                                '• does not try to teach you the Cantonese language - use other apps for that!',
                          ),
                        ],
                      ),
                    ],
                  ),
                  textAlign: TextAlign.left,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: Colors.black87,
                  ),
                ),
              ),
            ),
          ),
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Image.asset(
                  'assets/images/victoria_harbour_icon_new.png',
                  width: 140,
                  height: 140,
                ),
                const SizedBox(height: 8),
                const Text(
                  'Cantonese: Say it',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: Colors.white,
                    shadows: [
                      Shadow(
                        blurRadius: 6,
                        color: Colors.black54,
                        offset: Offset(0, 2),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Align(
            alignment: Alignment.bottomCenter,
            child: Padding(
              padding: const EdgeInsets.only(bottom: 48),
              child: ElevatedButton(
                onPressed: widget.onStart,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 12),
                ),
                child: const Text('Start'),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
