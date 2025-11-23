package org.example;

import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.startup.ProjectActivity;
import com.intellij.openapi.ui.Messages;
import com.intellij.openapi.wm.ToolWindow;
import com.intellij.openapi.wm.ToolWindowManager;
import org.jetbrains.annotations.Nullable;
import org.jetbrains.annotations.NotNull;
import kotlin.Unit;
import kotlin.coroutines.Continuation;
import java.awt.Robot;
import java.awt.event.InputEvent;
import javax.swing.*;
import javax.swing.text.JTextComponent;
import java.awt.*;
import java.awt.event.ActionEvent;
import java.awt.event.KeyEvent;


public class PromptActivity implements ProjectActivity {

    @Nullable
    @Override
    public Object execute(@NotNull Project project, @NotNull Continuation<? super Unit> continuation) {

        ApplicationManager.getApplication().invokeLater(() -> {

            ToolWindow aiToolWindow = ToolWindowManager.getInstance(project).getToolWindow("AIAssistant");

            if (aiToolWindow != null) {
                aiToolWindow.activate(() -> {

                    Component focusOwner = KeyboardFocusManager
                            .getCurrentKeyboardFocusManager()
                            .getFocusOwner();

                    Component target = isAiAssistantInput(focusOwner) ? focusOwner : findAiAssistantComponent(aiToolWindow.getComponent());

                    if (target instanceof JTextComponent) {
                        JTextComponent tc = (JTextComponent) target;

                        // 1. Postavite fokus
                        tc.requestFocusInWindow();
                        tc.setText("how are you");

                        // 2. Koristite Robot za simulaciju Enter-a
                        // Moramo biti u invokeLater bloku da bi osigurali da je UI postavljen
                        ApplicationManager.getApplication().invokeLater(() -> {
                            try {
                                Robot robot = new Robot();
                                robot.delay(100);

                                robot.keyPress(KeyEvent.VK_ENTER);
                                robot.keyRelease(KeyEvent.VK_ENTER);

                            } catch (AWTException e) {
                                e.printStackTrace();
                                Messages.showErrorDialog(project, "Robot creation failed: " + e.getMessage(), "Robot Error");
                            }
                        });

                    }
                });

            } else {
                Messages.showInfoMessage(project, "JetBrains AI Assistant not found or not active.", "Plugin Info");
            }
        });
        return Unit.INSTANCE;
    }
    private Component findAiAssistantComponent(Component component) {
        if (isAiAssistantInput(component)) {
            return component;
        }
        if (component instanceof Container) {
            for (Component child : ((Container) component).getComponents()) {
                Component found = findAiAssistantComponent(child);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }

    private boolean isAiAssistantInput(Component c) {
        if (c == null) return false;

        // AI Assistant chat always uses IntelliJ EditorComponentImpl
        if (!c.getClass().getName().contains("EditorComponentImpl")) {
            return false;
        }

        // Walk up the UI hierarchy looking for AI Assistant containers
        Component parent = c.getParent();
        while (parent != null) {
            String name = parent.getClass().getName().toLowerCase();
            if (name.contains("aiassistant") || name.contains("assistant")) {
                return true;
            }
            parent = parent.getParent();
        }

        return false;
    }


}

