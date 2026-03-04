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
            top: MediaQuery.of(context).size.height * 0.2,
            left: 16,
            right: 16,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'Cantonese: Say it',
                  style: TextStyle(
                    fontSize: 34,
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
                const SizedBox(height: 16),
                Center(
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
                            children: [
                              TextSpan(text: '• helps you learn to '),
                              TextSpan(text: 'recognise', style: TextStyle(fontWeight: FontWeight.w800)),
                              TextSpan(text: ' and '),
                              TextSpan(text: 'pronounce', style: TextStyle(fontWeight: FontWeight.w800)),
                              TextSpan(text: ' Cantonese\n'),
                              TextSpan(text: '• focuses on '),
                              TextSpan(text: 'spoken', style: TextStyle(fontWeight: FontWeight.w800)),
                              TextSpan(text: ' Cantonese\n'),
                              TextSpan(
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
