import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

enum TaskIntegrationApp { appleReminders }

extension TaskIntegrationAppExtension on TaskIntegrationApp {
  String get displayName {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return 'Apple Reminders';
    }
  }

  String get key {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return 'apple_reminders';
    }
  }

  IconData get icon {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return FontAwesomeIcons.apple;
    }
  }

  Color get iconColor {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return const Color(0xFF000000);
    }
  }
}

class TaskIntegrationsPage extends StatefulWidget {
  const TaskIntegrationsPage({super.key});

  @override
  State<TaskIntegrationsPage> createState() => _TaskIntegrationsPageState();
}

class _TaskIntegrationsPageState extends State<TaskIntegrationsPage> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    Future.microtask(() {
      if (mounted) {
        context.read<TaskIntegrationProvider>().initialize();
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      context.read<TaskIntegrationProvider>().initialize();
    }
  }

  Future<void> _selectApp(TaskIntegrationApp app) async {
    if (app == TaskIntegrationApp.appleReminders) {
      final appleRemindersService = AppleRemindersService();
      if (!appleRemindersService.hasPermission) {
        final shouldAuth = await _showAuthDialog(app);
        if (shouldAuth == true) {
          final success = await appleRemindersService.requestPermission();
          if (success) {
            await context.read<TaskIntegrationProvider>().setSelectedApp(app);
          }
        }
        return;
      }
    }

    await context.read<TaskIntegrationProvider>().setSelectedApp(app);
  }

  Future<bool?> _showAuthDialog(TaskIntegrationApp app) {
    return showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text(
            context.l10n.connectAppAuth(app.displayName),
            style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
          ),
          content: Text(
            context.l10n.connectAppAuthDescription(app.displayName),
            style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 14, height: 1.4),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: Text(
                context.l10n.cancel,
                style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 16, fontWeight: FontWeight.w500),
              ),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(
                context.l10n.continueButton,
                style: const TextStyle(color: Colors.blue, fontSize: 16, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<TaskIntegrationProvider>();
    final isLoading = provider.isLoading || !provider.hasLoaded;

    return Scaffold(
      backgroundColor: const Color(0xFF000000),
      appBar: AppBar(
        backgroundColor: const Color(0xFF000000),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(
          context.l10n.taskIntegrations,
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
        centerTitle: true,
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: ListView(
                  children: [
                    _buildAppTile(TaskIntegrationApp.appleReminders, isLoading),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(top: 20),
                child: Row(
                  children: [
                    const Icon(Icons.info_outline, color: Color(0xFF8E8E93), size: 16),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        context.l10n.integrationsFooter,
                        style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 12),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAppTile(TaskIntegrationApp app, bool isLoading) {
    final isSelected = context.watch<TaskIntegrationProvider>().selectedApp == app;
    final isConnected = context.watch<TaskIntegrationProvider>().isAppConnected(app);
    final isAvailable = PlatformService.isAppleRemindersSupported;

    return Opacity(
      opacity: isAvailable ? 1.0 : 0.5,
      child: InkWell(
        onTap: isAvailable && !isLoading
            ? () {
                if (!(isConnected && isSelected)) {
                  _selectApp(app);
                }
              }
            : null,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 16),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(app.icon, color: app.iconColor, size: 24),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      app.displayName,
                      style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                    ),
                    if (!isAvailable && app == TaskIntegrationApp.appleReminders)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          context.l10n.appleRemindersIosOnly,
                          style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 12),
                        ),
                      ),
                  ],
                ),
              ),
              if (isLoading)
                const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(color: Colors.white))
              else
                _buildCheckbox(isSelected: isSelected, isAvailable: isAvailable),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCheckbox({required bool isSelected, required bool isAvailable}) {
    return Container(
      width: 24,
      height: 24,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: isSelected ? Colors.blue : (isAvailable ? const Color(0xFF3C3C43) : Colors.transparent),
          width: 2,
        ),
        color: isSelected ? Colors.blue : Colors.transparent,
      ),
      child: isSelected ? const Icon(Icons.check, color: Colors.white, size: 14) : null,
    );
  }
}
