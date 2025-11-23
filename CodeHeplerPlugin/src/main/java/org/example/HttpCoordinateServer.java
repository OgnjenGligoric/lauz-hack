package org.example;

import com.intellij.ide.DataManager;
import com.intellij.openapi.actionSystem.CommonDataKeys;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.components.Service;
import com.intellij.openapi.diagnostic.Logger;
import com.intellij.openapi.editor.Editor;
import com.intellij.openapi.editor.LogicalPosition;
import com.intellij.openapi.fileEditor.FileEditorManager;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.ui.Messages;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.openapi.wm.ToolWindow;
import com.intellij.openapi.wm.ToolWindowManager;
import io.netty.bootstrap.ServerBootstrap;
import io.netty.buffer.Unpooled;
import io.netty.channel.*;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioServerSocketChannel;
import io.netty.handler.codec.http.*;
import io.netty.util.CharsetUtil;

import javax.swing.*;
import javax.swing.text.JTextComponent;
import java.awt.*;
import java.awt.event.KeyEvent;
import java.net.InetSocketAddress;
import java.util.List;
import java.util.Map;

import kotlin.Unit;
import kotlin.coroutines.Continuation;
import org.jetbrains.annotations.NotNull;
import org.json.JSONObject;
import io.netty.buffer.ByteBuf;
import io.netty.handler.codec.http.FullHttpRequest;
import io.netty.handler.codec.http.HttpResponseStatus;

@Service(Service.Level.APP)
public final class HttpCoordinateServer {

    private static final Logger LOG = Logger.getInstance(HttpCoordinateServer.class);
    private static final int PORT = 5005;
    private EventLoopGroup bossGroup;
    private EventLoopGroup workerGroup;
    private Channel channel;

    private boolean isRunning = false;

    public HttpCoordinateServer() {
        LOG.info("HttpCoordinateServer service initialized. Starting Netty server...");

        ApplicationManager.getApplication().executeOnPooledThread(this::startServer);
    }

    public void startServer() {
        if (isRunning) {
            LOG.info("HTTP server is already running.");
            return;
        }

        bossGroup = new NioEventLoopGroup(1);
        workerGroup = new NioEventLoopGroup();

        try {
            ServerBootstrap b = new ServerBootstrap();

            b.group(bossGroup, workerGroup)
                    .channel(NioServerSocketChannel.class)
                    .childHandler(new ChannelInitializer<SocketChannel>() {
                        @Override
                        protected void initChannel(SocketChannel ch) {
                            ChannelPipeline p = ch.pipeline();
                            p.addLast(new HttpServerCodec());
                            p.addLast(new HttpObjectAggregator(65536));
                            p.addLast(new HttpCoordinateHandler());
                        }
                    })
                    .option(ChannelOption.SO_BACKLOG, 128)
                    .childOption(ChannelOption.SO_KEEPALIVE, true);

            ChannelFuture future = b.bind(PORT);

            channel = future.sync().channel();

            if (future.isSuccess()) {
                isRunning = true;
                LOG.info("Bound Address: " + ((InetSocketAddress)channel.localAddress()).getHostString()
                        + ":" + ((InetSocketAddress)channel.localAddress()).getPort());
            } else {
                stopServer();
            }

        } catch (Exception e) {
            stopServer();
        }
    }

    public void stopServer() {
        LOG.info("Stopping HTTP server...");
        if (channel != null) {
            channel.close();
            channel = null;
        }
        if (bossGroup != null) bossGroup.shutdownGracefully();
        if (workerGroup != null) workerGroup.shutdownGracefully();
        LOG.info("HTTP server stopped.");
    }

    private static class HttpCoordinateHandler extends SimpleChannelInboundHandler<FullHttpRequest> {

        @Override
        protected void channelRead0(ChannelHandlerContext ctx, FullHttpRequest request) {
            try {
                ByteBuf content = request.content();
                String body = content.toString(java.nio.charset.StandardCharsets.UTF_8);

                JSONObject json = new JSONObject(body);

                String action = json.optString("action", "unknown");

                switch (action) {
                    case "swipe_up" -> {
                        scrollUp();
                    }
                    case "swipe_down" -> {
                        scrollDown();
                    }
                    case "swipe_left" -> {
                        previousTab();
                    }
                    case "swipe_right" -> {
                        nextTab();
                    }
                    case "special_pose" -> {
                        String responseText = handleHandSpecialPose(json);
                        sendResponse(ctx, HttpResponseStatus.OK, responseText);
                        return;
                    }
                    default -> {
                        System.out.println("Unknown action: " + action);
                    }
                }

                sendResponse(ctx, HttpResponseStatus.OK, "{\"status\":\"ok\"}");

            } catch (Exception ex) {
                ex.printStackTrace();
                sendError(ctx, HttpResponseStatus.BAD_REQUEST);
            }
        }

        private String handleHandSpecialPose(JSONObject json) {
            if (!json.has("coordinates")) return "{\"error\": \"missing coordinates\"}";

            JSONObject coords = json.getJSONObject("coordinates");
            if (!coords.has("x") || !coords.has("y")) return "{\"error\": \"invalid coordinates\"}";

            int x = coords.getInt("x");
            int y = coords.getInt("y");

            final int[] lineNumberHolder = { -1 };
            final StringBuilder fileTextHolder = new StringBuilder();

            ApplicationManager.getApplication().invokeAndWait(() -> {
                Editor editor = CommonDataKeys.EDITOR.getData(DataManager.getInstance().getDataContext());
                if (editor == null) return;

                JComponent editorComponent = editor.getContentComponent();
                Point screenPoint = new Point(x, y);
                SwingUtilities.convertPointFromScreen(screenPoint, editorComponent);

                LogicalPosition pos = editor.xyToLogicalPosition(screenPoint);
                lineNumberHolder[0] = pos.line;

                fileTextHolder.append(editor.getDocument().getText());
            });

            String prompt = "Explain the code and it's context around line " + lineNumberHolder[0];
            execute(prompt);

            return "{ \"lineNumber\": " + lineNumberHolder[0] +
                    ", \"fileText\": " + JSONObject.quote(fileTextHolder.toString()) + " }";
        }

        private void scrollUp() {
            ApplicationManager.getApplication().invokeLater(() -> {
                Editor editor = CommonDataKeys.EDITOR.getData(DataManager.getInstance().getDataContext());
                if (editor == null) return;

                var scrollingModel = editor.getScrollingModel();
                var visibleArea = scrollingModel.getVisibleArea();

                int delta = (int)(visibleArea.height * 0.66);

                scrollingModel.scrollVertically(visibleArea.y - delta);
            });
        }

        private void scrollDown() {
            ApplicationManager.getApplication().invokeLater(() -> {
                Editor editor = CommonDataKeys.EDITOR.getData(DataManager.getInstance().getDataContext());
                if (editor == null) return;

                var scrollingModel = editor.getScrollingModel();
                var visibleArea = scrollingModel.getVisibleArea();

                int delta = (int)(visibleArea.height * 0.66);

                scrollingModel.scrollVertically(visibleArea.y + delta);
            });
        }

        public static void nextTab() {
            ApplicationManager.getApplication().invokeLater(() -> {
                Project project = CommonDataKeys.PROJECT.getData(
                        DataManager.getInstance().getDataContext()
                );
                if (project == null) return;

                FileEditorManager fem = FileEditorManager.getInstance(project);
                VirtualFile[] files = fem.getOpenFiles();
                if (files.length == 0) return;

                VirtualFile current = fem.getSelectedFiles().length > 0
                        ? fem.getSelectedFiles()[0]
                        : null;

                int index = -1;
                for (int i = 0; i < files.length; i++) {
                    if (files[i].equals(current)) {
                        index = i;
                        break;
                    }
                }

                int nextIndex = (index + 1) % files.length;
                fem.openFile(files[nextIndex], true);
            });
        }

        public static void previousTab() {
            ApplicationManager.getApplication().invokeLater(() -> {
                Project project = CommonDataKeys.PROJECT.getData(
                        DataManager.getInstance().getDataContext()
                );
                if (project == null) return;

                FileEditorManager fem = FileEditorManager.getInstance(project);
                VirtualFile[] files = fem.getOpenFiles();
                if (files.length == 0) return;

                VirtualFile current = fem.getSelectedFiles().length > 0
                        ? fem.getSelectedFiles()[0]
                        : null;

                int index = -1;
                for (int i = 0; i < files.length; i++) {
                    if (files[i].equals(current)) {
                        index = i;
                        break;
                    }
                }

                int prevIndex = (index - 1 + files.length) % files.length;
                fem.openFile(files[prevIndex], true);
            });
        }

        private void sendResponse(ChannelHandlerContext ctx, HttpResponseStatus status, String content) {
            FullHttpResponse response = new DefaultFullHttpResponse(
                    HttpVersion.HTTP_1_1,
                    status,
                    Unpooled.copiedBuffer(content, CharsetUtil.UTF_8));

            response.headers().set(HttpHeaderNames.CONTENT_TYPE, "text/plain; charset=UTF-8");
            response.headers().setInt(HttpHeaderNames.CONTENT_LENGTH, response.content().readableBytes());

            ctx.writeAndFlush(response).addListener(ChannelFutureListener.CLOSE);
        }

        private void sendError(ChannelHandlerContext ctx, HttpResponseStatus status) {
            sendResponse(ctx, status, "Failure: " + status.reasonPhrase());
        }

        public Object execute(String prompt) {

            ApplicationManager.getApplication().invokeLater(() -> {
                Project project = CommonDataKeys.PROJECT.getData(
                        DataManager.getInstance().getDataContext()
                );
                if (project == null) return;

                ToolWindow aiToolWindow = ToolWindowManager.getInstance(project).getToolWindow("AIAssistant");

                if (aiToolWindow != null) {
                    aiToolWindow.activate(() -> {

                        Component focusOwner = KeyboardFocusManager
                                .getCurrentKeyboardFocusManager()
                                .getFocusOwner();

                        Component target = isAiAssistantInput(focusOwner) ? focusOwner : findAiAssistantComponent(aiToolWindow.getComponent());

                        if (target instanceof JTextComponent) {
                            JTextComponent tc = (JTextComponent) target;

                            tc.requestFocusInWindow();
                            tc.setText(prompt);

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

            if (!c.getClass().getName().contains("EditorComponentImpl")) {
                return false;
            }

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
}