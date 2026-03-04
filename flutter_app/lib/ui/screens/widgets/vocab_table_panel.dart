import 'package:flutter/material.dart';
import '../../cubits/shared/vocab_row.dart';

class VocabTablePanel extends StatefulWidget {
  final List<VocabRow> rows;
  final String searchQuery;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<VocabRow> onSelectRow;

  const VocabTablePanel({
    super.key,
    required this.rows,
    required this.searchQuery,
    required this.onSearchChanged,
    required this.onSelectRow,
  });

  @override
  State<VocabTablePanel> createState() => _VocabTablePanelState();
}

class _VocabTablePanelState extends State<VocabTablePanel> {
  final ScrollController _controller = ScrollController();
  bool _showBottomFade = false;
  bool _showTopFade = false;
  bool _fadeUpdateScheduled = false;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_scheduleFadeUpdate);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scheduleFadeUpdate();
    });
  }

  @override
  void dispose() {
    _controller.removeListener(_scheduleFadeUpdate);
    _controller.dispose();
    super.dispose();
  }

  void _scheduleFadeUpdate() {
    if (_fadeUpdateScheduled) {
      return;
    }
    _fadeUpdateScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _fadeUpdateScheduled = false;
      _updateFadeState();
    });
  }

  void _updateFadeState() {
    if (!_controller.hasClients) {
      return;
    }
    final pos = _controller.position;
    final canScroll = pos.maxScrollExtent > 0;
    final showTop = canScroll && pos.pixels > 1;
    final showBottom = canScroll && pos.pixels < (pos.maxScrollExtent - 1);
    if (showTop != _showTopFade || showBottom != _showBottomFade) {
      setState(() {
        _showTopFade = showTop;
        _showBottomFade = showBottom;
      });
    }
  }

  @override
  void didUpdateWidget(covariant VocabTablePanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.rows != widget.rows || oldWidget.searchQuery != widget.searchQuery) {
      _scheduleFadeUpdate();
    }
  }

  @override
  Widget build(BuildContext context) {
    final query = widget.searchQuery.trim().toLowerCase();
    final filtered = query.isEmpty ? widget.rows : widget.rows.where((row) {
      final hay = [
        row.hanzi,
        row.jyutping,
        row.meanings.join(' '),
        row.categories.join(' '),
      ].join(' ').toLowerCase();
      return hay.contains(query);
    }).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          decoration: InputDecoration(
            isDense: true,
            contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            labelText: 'Search (Hanzi / Jyutping / meaning)',
            suffixIcon: widget.searchQuery.isEmpty
                ? null
                : IconButton(
                    tooltip: 'Clear search',
                    icon: const Icon(Icons.close, size: 16),
                    onPressed: () {
                      widget.onSearchChanged('');
                      FocusScope.of(context).unfocus();
                    },
                  ),
          ),
          style: const TextStyle(fontSize: 12),
          onChanged: widget.onSearchChanged,
        ),
        const SizedBox(height: 8),
        if (filtered.isEmpty)
          const Expanded(
            child: Center(child: Text('No matches')),
          )
        else
          Expanded(
            child: Stack(
              children: [
                ListView.separated(
                  controller: _controller,
                  itemCount: filtered.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final row = filtered[index];
                    final cats = row.categories.isEmpty ? '' : row.categories.join(', ');
                    final meanings = row.meanings.isEmpty ? '' : row.meanings.join(', ');
                    return ListTile(
                      dense: true,
                      contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      title: Row(
                        children: [
                          Flexible(
                            child: Text(
                              row.hanzi,
                              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Flexible(
                            child: Text(
                              row.jyutping,
                              style: const TextStyle(fontSize: 12, color: Colors.black54),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                      subtitle: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (meanings.isNotEmpty) Text(meanings, style: const TextStyle(fontSize: 11)),
                          if (cats.isNotEmpty)
                            Text('Categories: $cats', style: const TextStyle(fontSize: 10)),
                        ],
                      ),
                      onTap: () => widget.onSelectRow(row),
                    );
                  },
                ),
                if (_showTopFade)
                  Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    height: 12,
                    child: IgnorePointer(
                      child: Container(
                        decoration: const BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [Color(0xFFF8EDE1), Color(0x00F8EDE1)],
                          ),
                        ),
                      ),
                    ),
                  ),
                if (_showBottomFade)
                  Positioned(
                    left: 0,
                    right: 0,
                    bottom: 0,
                    height: 16,
                    child: IgnorePointer(
                      child: Container(
                        decoration: const BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.bottomCenter,
                            end: Alignment.topCenter,
                            colors: [Color(0xFFF8EDE1), Color(0x00F8EDE1)],
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
      ],
    );
  }
}
