import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../cubits/main/main_cubit.dart';
import '../../cubits/main/main_state.dart';

class MainScreen extends StatelessWidget {
  const MainScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => MainCubit()..loadData(),
      child: const MainView(),
    );
  }
}

class MainView extends StatelessWidget {
  const MainView();

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<MainCubit, MainState>(
      builder: (context, state) {
        return Scaffold(
          appBar: AppBar(
            title: const Text('My Cantonese Words'),
            automaticallyImplyLeading: false,
            actions: [
              Builder(
                builder: (ctx) => IconButton(
                  tooltip: 'Menu',
                  icon: const Icon(Icons.menu),
                  onPressed: () => Scaffold.of(ctx).openDrawer(),
                ),
              ),
              IconButton(
                tooltip: 'Search',
                icon: const Icon(Icons.search),
                onPressed: () {},
              ),
            ],
          ),
          drawer: _buildDrawer(context, state),
          body: Column(
            children: [
              Expanded(
                child: state.loading
                    ? const Center(child: CircularProgressIndicator())
                    : SingleChildScrollView(
                        padding: const EdgeInsets.all(18),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            if (state.errorMessage != null) ...[
                              Text(
                                state.errorMessage!,
                                style: const TextStyle(color: Colors.red),
                              ),
                              const SizedBox(height: 8),
                            ],
                            _JyutpingField(value: state.jyutping),
                            const SizedBox(height: 8),
                            _CategoryRow(
                              categories: state.categories,
                              value: state.selectedCategory,
                              enabled: !state.autoMode,
                              onChanged: (value) => context.read<MainCubit>().setCategory(value),
                            ),
                            const SizedBox(height: 8),
                            _HanziDisplay(
                              text: state.hanzi,
                              highlightIndex: state.highlightIndex,
                            ),
                            const SizedBox(height: 8),
                            _GroupBox(
                              title: 'Transliteration (Jyutping)',
                              compact: true,
                              child: _ToneRow(
                                blocks: state.toneBlocks,
                                onTap: (idx) => context.read<MainCubit>().playSyllable(idx),
                              ),
                            ),
                            const SizedBox(height: 8),
                            _GroupBox(
                              title: 'Translation',
                              child: _MeaningsField(meanings: state.meanings),
                            ),
                            const SizedBox(height: 8),
                            // Sound and Tone Mastery removed.
                          ],
                        ),
                      ),
              ),
              Padding(
                padding: const EdgeInsets.only(bottom: 32),
                child: _BottomBar(
                  tortoise: state.tortoise,
                  autoMode: state.autoMode,
                  ttsArmed: state.ttsArmed,
                  isPlaying: state.isPlaying,
                  onPrev: () => context.read<MainCubit>().prevItem(),
                  onPlay: () => context.read<MainCubit>().playSequence(),
                  onNext: () => context.read<MainCubit>().nextItem(),
                  onTortoiseChanged: (v) => context.read<MainCubit>().toggleTortoise(v),
                  onAutoChanged: (v) => context.read<MainCubit>().toggleAuto(v),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Drawer _buildDrawer(BuildContext context, MainState state) {
    return Drawer(
      child: Container(
        color: Theme.of(context).colorScheme.surfaceVariant,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(8, 44, 8, 8),
          children: [
            const SizedBox(height: 18),
            _GroupBox(
              title: 'WPM (60-220): ${state.wpm}',
              compact: true,
              child: Slider(
                value: state.wpm.toDouble(),
                min: 60,
                max: 220,
                divisions: 8,
                label: '${state.wpm}',
                onChanged: (v) => context.read<MainCubit>().setWpm(v.round()),
              ),
            ),
            const SizedBox(height: 8),
            _GroupBox(
              title: 'Repeats (1-10): ${state.repeats}',
              compact: true,
              child: Slider(
                value: state.repeats.toDouble(),
                min: 1,
                max: 10,
                divisions: 9,
                label: '${state.repeats}',
                onChanged: (v) => context.read<MainCubit>().setRepeats(v.round()),
              ),
            ),
            const SizedBox(height: 8),
            _DisclosureButton(
              title: 'Delays (Advanced)',
              expanded: state.showDelays,
              onTap: () => context.read<MainCubit>().toggleDelays(),
              textColor: Colors.black,
            ),
            if (state.showDelays) ...[
              const SizedBox(height: 8),
              _DelaySlider(
                label: 'Intro delay (0-10): ${state.introDelay}',
                value: state.introDelay,
                onChanged: (v) => context.read<MainCubit>().setIntroDelay(v),
              ),
              _DelaySlider(
                label: 'Repeat delay (0-10): ${state.repeatDelay}',
                value: state.repeatDelay,
                onChanged: (v) => context.read<MainCubit>().setRepeatDelay(v),
              ),
              _DelaySlider(
                label: 'Extro delay (0-10): ${state.extroDelay}',
                value: state.extroDelay,
                onChanged: (v) => context.read<MainCubit>().setExtroDelay(v),
              ),
              _DelaySlider(
                label: 'Auto delay (0-10): ${state.autoDelay}',
                value: state.autoDelay,
                onChanged: (v) => context.read<MainCubit>().setAutoDelay(v),
              ),
            ],
            const SizedBox(height: 8),
            _GroupBox(
              title: 'Voices',
              compact: true,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  RadioListTile<String>(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: const Text('macOS (Sinji)'),
                    value: 'macos',
                    groupValue: state.ttsEngine,
                    onChanged: (v) => context.read<MainCubit>().setTtsEngine(v ?? 'macos'),
                  ),
                  RadioListTile<String>(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Google (Cantonese)'),
                    value: 'google',
                    groupValue: state.ttsEngine,
                    onChanged: state.googleAvailable
                        ? (v) => context.read<MainCubit>().setTtsEngine(v ?? 'google')
                        : null,
                  ),
                  DropdownButtonFormField<String>(
                    value: state.selectedGoogleVoice,
                    isExpanded: true,
                    items: state.googleVoices
                        .map(
                          (v) => DropdownMenuItem<String>(
                            value: v['name'],
                            child: Text(
                              v['label'] ?? v['name'] ?? '',
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        )
                        .toList(),
                    onChanged: state.ttsEngine == 'google'
                        ? (v) => context.read<MainCubit>().setGoogleVoice(v)
                        : null,
                  ),
                  const SizedBox(height: 8),
                  ElevatedButton(
                    onPressed: () => context.read<MainCubit>().playOnce(),
                    child: const Text('Audio Test (🔊 你好)'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),
            _DisclosureButton(
              title: 'About',
              expanded: state.showAbout,
              onTap: () => context.read<MainCubit>().toggleAbout(),
              textColor: Colors.black,
            ),
            if (state.showAbout) ...[
              const SizedBox(height: 8),
              _GroupBox(
                title: 'About',
                compact: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    SizedBox(
                      height: 140,
                      child: SingleChildScrollView(
                        child: Text(state.aboutText),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 8),
            OutlinedButton(
              key: const Key('btnReset'),
              onPressed: () => context.read<MainCubit>().resetSettings(),
              child: const Text('Reset'),
            ),
          ],
        ),
      ),
    );
  }
}

class _JyutpingField extends StatelessWidget {
  final String value;

  const _JyutpingField({required this.value});

  @override
  Widget build(BuildContext context) {
    return TextField(
      readOnly: true,
      decoration: const InputDecoration(
        hintText: 'nei5 hou2',
      ),
      style: const TextStyle(fontSize: 32),
      controller: TextEditingController(text: value),
    );
  }
}

class _CategoryRow extends StatelessWidget {
  final List<String> categories;
  final String value;
  final ValueChanged<String> onChanged;
  final bool enabled;

  const _CategoryRow({
    required this.categories,
    required this.value,
    required this.onChanged,
    required this.enabled,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const SizedBox(width: 8),
        const Text('Category:'),
        const SizedBox(width: 8),
        Expanded(
          child: DropdownButtonFormField<String>(
            value: value,
            isExpanded: true,
            onChanged: enabled ? (v) => v == null ? null : onChanged(v) : null,
            items: categories
                .map(
                  (c) => DropdownMenuItem<String>(
                    value: c,
                    child: Text(c, overflow: TextOverflow.ellipsis),
                  ),
                )
                .toList(),
          ),
        ),
      ],
    );
  }
}

class _HanziDisplay extends StatelessWidget {
  final String text;
  final int? highlightIndex;

  const _HanziDisplay({
    required this.text,
    required this.highlightIndex,
  });

  @override
  Widget build(BuildContext context) {
    final chars = text.runes.map((r) => String.fromCharCode(r)).toList();
    final highlight = highlightIndex ?? -1;
    final spans = <TextSpan>[];
    for (var i = 0; i < chars.length; i++) {
      spans.add(TextSpan(
        text: chars[i],
        style: TextStyle(color: i == highlight ? const Color(0xFFC53030) : null),
      ));
    }
    return Container(
      alignment: Alignment.center,
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: FittedBox(
        fit: BoxFit.scaleDown,
        child: Text.rich(
          TextSpan(children: spans),
          style: const TextStyle(fontSize: 72, fontWeight: FontWeight.w600),
        ),
      ),
    );
  }
}

class _GroupBox extends StatelessWidget {
  final String title;
  final Widget child;
  final bool compact;

  const _GroupBox({
    required this.title,
    required this.child,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final titleGap = compact ? 4.0 : 8.0;
    return Container(
      padding: compact ? const EdgeInsets.fromLTRB(8, 8, 8, 2) : const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border.all(color: theme.colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            title,
            style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
          ),
          SizedBox(height: titleGap),
          child,
        ],
      ),
    );
  }
}

class _ToneRow extends StatelessWidget {
  final List<ToneBlock> blocks;
  final ValueChanged<int> onTap;

  const _ToneRow({
    required this.blocks,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    if (blocks.isEmpty) {
      return const SizedBox.shrink();
    }
    return GridView.builder(
      itemCount: blocks.length,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        mainAxisSpacing: 2,
        crossAxisSpacing: 8,
        childAspectRatio: 1.35,
      ),
      itemBuilder: (context, index) {
        return ToneBlockTile(
          block: blocks[index],
          onTap: () => onTap(index),
        );
      },
    );
  }
}

class ToneBlockTile extends StatelessWidget {
  final ToneBlock block;
  final VoidCallback onTap;

  const ToneBlockTile({
    required this.block,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final tone = block.tone;
    final asset = tone > 0 ? 'assets/images/tone_$tone.png' : null;
    final tip = block.hint.isEmpty
        ? 'Sounds like: ${block.label}'
        : 'Sounds like: ${block.label}\nHint: ${block.hint}';
    return Tooltip(
      message: tip,
      child: InkWell(
        onTap: onTap,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final imageHeight = constraints.maxHeight * 0.5;
            return Container(
              padding: const EdgeInsets.all(2),
              decoration: BoxDecoration(
                border: Border.all(color: Theme.of(context).colorScheme.outline),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Column(
                children: [
                  Expanded(
                    flex: 2,
                    child: Center(
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(
                          block.label,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                      ),
                    ),
                  ),
                  Expanded(
                    flex: 3,
                    child: Container(
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.surfaceVariant,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: asset == null
                          ? Text('Tone ${block.tone}')
                          : Image.asset(asset, fit: BoxFit.contain),
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _MeaningsField extends StatelessWidget {
  final List<String> meanings;

  const _MeaningsField({required this.meanings});

  @override
  Widget build(BuildContext context) {
    return TextField(
      readOnly: true,
      maxLines: 3,
      controller: TextEditingController(text: meanings.join(', ')),
      decoration: const InputDecoration(hintText: 'Meanings will appear here...'),
    );
  }
}

class _BottomBar extends StatelessWidget {
  final bool tortoise;
  final bool autoMode;
  final bool ttsArmed;
  final bool isPlaying;
  final VoidCallback onPrev;
  final VoidCallback onPlay;
  final VoidCallback onNext;
  final ValueChanged<bool> onTortoiseChanged;
  final ValueChanged<bool> onAutoChanged;

  const _BottomBar({
    required this.tortoise,
    required this.autoMode,
    required this.ttsArmed,
    required this.isPlaying,
    required this.onPrev,
    required this.onPlay,
    required this.onNext,
    required this.onTortoiseChanged,
    required this.onAutoChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        border: Border(top: BorderSide(color: Theme.of(context).colorScheme.outlineVariant)),
      ),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          ElevatedButton(
            key: const Key('btnPrev'),
            onPressed: (!isPlaying && ttsArmed && !autoMode) ? onPrev : null,
            style: ElevatedButton.styleFrom(
              minimumSize: const Size(40, 32),
              padding: EdgeInsets.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Icon(Icons.chevron_left),
          ),
          ElevatedButton(
            key: const Key('btnPlay'),
            onPressed: (!isPlaying && !autoMode) ? onPlay : null,
            style: ElevatedButton.styleFrom(
              minimumSize: const Size(56, 32),
              padding: const EdgeInsets.symmetric(horizontal: 10),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: Text(ttsArmed ? 'Repeat' : 'Play'),
          ),
          ElevatedButton(
            key: const Key('btnNext'),
            onPressed: (!isPlaying && ttsArmed && !autoMode) ? onNext : null,
            style: ElevatedButton.styleFrom(
              minimumSize: const Size(40, 32),
              padding: EdgeInsets.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Icon(Icons.chevron_right),
          ),
          FilterChip(
            key: const Key('chipSlow'),
            selected: tortoise,
            label: const Text('Slow'),
            onSelected: (!isPlaying && ttsArmed && !autoMode) ? onTortoiseChanged : null,
            visualDensity: VisualDensity.compact,
            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            labelPadding: const EdgeInsets.symmetric(horizontal: 6),
          ),
          FilterChip(
            key: const Key('chipAuto'),
            selected: autoMode,
            label: const Text('Auto'),
            onSelected: (ttsArmed || autoMode) ? onAutoChanged : null,
            visualDensity: VisualDensity.compact,
            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            labelPadding: const EdgeInsets.symmetric(horizontal: 6),
          ),
        ],
      ),
    );
  }
}

class _DisclosureButton extends StatelessWidget {
  final String title;
  final bool expanded;
  final VoidCallback onTap;
  final Color? textColor;

  const _DisclosureButton({
    required this.title,
    required this.expanded,
    required this.onTap,
    this.textColor,
  });

  @override
  Widget build(BuildContext context) {
    final icon = expanded ? '▼' : '▶';
    return TextButton(
      onPressed: onTap,
      child: Row(
        children: [
          Text(icon, style: TextStyle(color: textColor)),
          const SizedBox(width: 8),
          Expanded(child: Text(title, style: TextStyle(color: textColor))),
        ],
      ),
    );
  }
}

class _DelaySlider extends StatelessWidget {
  final String label;
  final int value;
  final ValueChanged<int> onChanged;

  const _DelaySlider({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return _GroupBox(
      title: label,
      compact: true,
      child: Slider(
        value: value.toDouble(),
        min: 0,
        max: 10,
        divisions: 10,
        label: '$value',
        onChanged: (v) => onChanged(v.round()),
      ),
    );
  }
}
