package org.example;

import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.startup.ProjectActivity;
import com.intellij.openapi.wm.ToolWindow;
import com.intellij.openapi.wm.ToolWindowManager;
import com.intellij.openapi.ui.Messages;
import kotlin.Unit;
import kotlin.coroutines.Continuation;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import javax.swing.text.JTextComponent;
import java.awt.*;

public class PromptActivity implements ProjectActivity {

    @Nullable
    @Override
    public Object execute(@NotNull Project project, @NotNull Continuation<? super Unit> continuation) {

        System.out.println("[PromptActivity] execute() START");

        // Ensure the server service is started
        System.out.println("[PromptActivity] Starting HttpCoordinateServer service...");
        ApplicationManager.getApplication().getService(HttpCoordinateServer.class);
        System.out.println("[PromptActivity] HttpCoordinateServer started.");

        ApplicationManager.getApplication().invokeLater(() -> {
            System.out.println("[PromptActivity] invokeLater() START");

            // 1. Try to find the JetBrains AI Assistant Tool Window
            System.out.println("[PromptActivity] Looking for AI Assistant ToolWindow...");
            ToolWindow aiToolWindow = ToolWindowManager.getInstance(project).getToolWindow("AIAssistant");

            if (aiToolWindow != null) {
                System.out.println("[PromptActivity] AIAssistant ToolWindow FOUND");

                // 2. If found, activate (open) it automatically
                aiToolWindow.activate(() -> {
                    System.out.println("[PromptActivity] AIAssistant activated, checking focusOwner...");

                    Component focusOwner = KeyboardFocusManager
                            .getCurrentKeyboardFocusManager()
                            .getFocusOwner();

                    if (focusOwner == null) {
                        System.out.println("[PromptActivity] focusOwner = NULL");
                        return;
                    }

                    System.out.println("[PromptActivity] focusOwner class = " + focusOwner.getClass().getName());

                    // Case 1: Standard Swing text component (search bars, fields, dialogs, etc.)
                    if (focusOwner instanceof JTextComponent) {
                        System.out.println("[PromptActivity] focusOwner is JTextComponent — writing text...");
                        JTextComponent tc = (JTextComponent) focusOwner;

                        ApplicationManager.getApplication().invokeLater(() -> {
                            System.out.println("[PromptActivity] Writing 'how are you' into text field...");
                            tc.setText("how are you");
                        });

                        return;
                    }

                    System.out.println("[PromptActivity] focusOwner is NOT a text field.");
                });

            } else {
                System.out.println("[PromptActivity] AIAssistant ToolWindow NOT FOUND");
                Messages.showInfoMessage(project, "JetBrains AI Assistant not found or not active.", "Plugin Info");
            }

            System.out.println("[PromptActivity] invokeLater() END");
        });

        System.out.println("[PromptActivity] execute() END");
        return Unit.INSTANCE;
    }
}
