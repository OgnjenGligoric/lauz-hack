package org.example;

import com.intellij.ide.DataManager;
import com.intellij.openapi.actionSystem.AnAction;
import com.intellij.openapi.actionSystem.AnActionEvent;
import com.intellij.openapi.actionSystem.CommonDataKeys;
import com.intellij.openapi.editor.Editor;
import com.intellij.openapi.editor.LogicalPosition;
import com.intellij.openapi.ide.CopyPasteManager;
import com.intellij.openapi.ui.Messages;

import javax.swing.*;
import java.awt.*;
import java.awt.datatransfer.StringSelection;

public class PrintLineAction extends AnAction {

    // Action is now a simple informational message
    @Override
    public void actionPerformed(AnActionEvent e) {
        Messages.showMessageDialog("A custom HTTP server is running on port 5005. Use it to send coordinates.", "Info", Messages.getInformationIcon());
    }

    // This method is called by the Netty Http Server thread
    public static void handleCoordinates(int screenX, int screenY) {
        // DataContext must be retrieved on the EDT
        Editor editor = CommonDataKeys.EDITOR.getData(
                DataManager.getInstance().getDataContext()
        );

        if (editor == null) {
            System.out.println("No active editor");
            return;
        }

        JComponent editorComponent = editor.getContentComponent();

        Point screenPoint = new Point(screenX, screenY);
        SwingUtilities.convertPointFromScreen(screenPoint, editorComponent);

        LogicalPosition pos = editor.xyToLogicalPosition(screenPoint);

        int lineNumber = pos.line;
        int startOffset = editor.getDocument().getLineStartOffset(lineNumber);
        int endOffset = editor.getDocument().getLineEndOffset(lineNumber);

        String lineText = editor.getDocument().getText().substring(startOffset, endOffset);

        CopyPasteManager.getInstance().setContents(new StringSelection(lineText));

        System.out.println("Copied line " + lineNumber + ": " + lineText);
    }
}