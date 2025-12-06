$(document).ready(function() {
    var socket = io();
    var currentPrivateUser = null; // {id, username}
        var privateHistory = {}; // { uid: [ {data object}, ... ] }
    
    // Make private chat modal draggable
    dragElement(document.getElementById("private-chat-modal"));
    
    // Emoji List
    const emojis = [
        "😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣", "😊", "😇",
        "🙂", "🙃", "😉", "😌", "😍", "🥰", "😘", "😗", "😙", "😚",
        "😋", "😛", "😝", "😜", "🤪", "🤨", "🧐", "🤓", "😎", "🤩",
        "🥳", "😏", "😒", "😞", "😔", "😟", "😕", "🙁", "☹️", "😣",
        "😖", "😫", "😩", "🥺", "😢", "😭", "😤", "😠", "😡", "🤬",
        "🤯", "😳", "🥵", "🥶", "😱", "😨", "😰", "😥", "😓", "🤗",
        "🤔", "🤭", "🤫", "🤥", "😶", "😐", "😑", "😬", "🙄", "😯",
        "😦", "😧", "😮", "😲", "🥱", "😴", "🤤", "😪", "😵", "🤐",
        "🥴", "🤢", "🤮", "🤧", "😷", "🤒", "🤕", "🤑", "🤠", "😈",
        "👍", "👎", "👌", "✌️", "🤞", "🤟", "🤘", "🤙", "👈", "👉",
        "👆", "👇", "✋", "🤚", "🖐", "🖖", "👋", "🤙", "💪", "🦾",
        "🙏", "🤝", "💅", "👂", "👃", "🧠", "🦷", "🦴", "👀", "👁️",
        "💋", "👄", "👅", "💄", "💔", "❤️", "🧡", "💛", "💚", "💙",
        "💜", "🤎", "🖤", "🤍", "💯", "💢", "💥", "💫", "💦", "💨"
    ];
    
    // Render Emojis
    var $emojiGrid = $('#emoji-grid');
    emojis.forEach(function(emoji) {
        var $span = $('<span>' + emoji + '</span>');
        $span.click(function() {
            var $input = $('#msg-input');
            $input.val($input.val() + emoji);
            $('#emoji-picker').hide();
            $input.focus();
        });
        $emojiGrid.append($span);
    });

    // --- Socket Events ---
    socket.on('connect', function() {
        console.log('Connected to chat server');
    });

    socket.on('update_user_list', function(users) {
        renderUserList(users);
    });

    socket.on('receive_message', function(data) {
        if (data.is_private) {
            handlePrivateMessage(data);
        } else {
            appendMessage('#chat-messages', data);
        }
    });

    // --- UI Interactions ---
    
    // Send Public Message
    $('#btn-send').click(sendPublicMessage);
    $('#msg-input').keypress(function(e) {
        if(e.which == 13 && !e.shiftKey) {
            e.preventDefault();
            sendPublicMessage();
        }
    });

    // Send Private Message
    $('#pc-send').click(sendPrivateMessage);
    $('#pc-input').keypress(function(e) {
        if(e.which == 13) {
            e.preventDefault();
            sendPrivateMessage();
        }
    });

    // Close Private Chat
    $('#pc-close').click(function() {
        $('#private-chat-modal').hide();
        currentPrivateUser = null;
    });

    // Emoji Picker
    $('#emoji-btn').click(function(e) {
        e.stopPropagation();
        $('#emoji-picker').toggle();
    });

    $(document).click(function() {
        $('#emoji-picker').hide();
    });

    $('#emoji-picker').click(function(e) {
        e.stopPropagation();
    });
    
    // Removed duplicate click handler since it's now handled in the render loop
    // $('.emoji-grid span').click(...) 

    // History Button
    $('#btn-history').click(function() {
        if(typeof layer !== 'undefined') {
            layer.msg('功能正在建设中');
        } else {
            alert('功能正在建设中');
        }
    });

    // Mobile Toggle
    $('#toggle-users').click(function() {
        $('#chat-users').toggleClass('show');
    });

    // --- Functions ---

    function sendPublicMessage() {
        var content = $('#msg-input').val().trim();
        if(!content) return;
        
        socket.emit('send_message', {
            content: content,
            to_user_id: null
        });
        $('#msg-input').val('');
    }

    function sendPrivateMessage() {
        if (!currentPrivateUser) return;
        var content = $('#pc-input').val().trim();
        if(!content) return;
        
        socket.emit('send_message', {
            content: content,
            to_user_id: currentPrivateUser.id
        });
        $('#pc-input').val('');
    }

    function renderUserList(users) {
        var $list = $('#users-list');
        $list.empty();
        $('#online-count').text(users.length);
        
        var showLimit = 10;
        var visibleUsers = users.slice(0, showLimit);
        var hiddenUsers = users.slice(showLimit);

        visibleUsers.forEach(function(u) {
            appendUserItem($list, u);
        });

        if (hiddenUsers.length > 0) {
            var $more = $('<div class="user-more">更多 ' + hiddenUsers.length + ' 人</div>');
            $more.click(function() {
                $(this).remove();
                hiddenUsers.forEach(function(u) {
                    appendUserItem($list, u);
                });
            });
            $list.append($more);
        }
    }

    function appendUserItem($container, u) {
        var isSelf = (u.id === CURRENT_USER_ID);
        var $item = $('<div class="user-item" data-uid="' + u.id + '"></div>');
        var $avatar = $('<div class="user-avatar">' + u.username.substring(0,1).toUpperCase() + '<span class="red-dot"></span></div>');
        $item.append($avatar);
        $item.append('<div class="user-name">' + escapeHtml(u.username) + (isSelf ? ' (我)' : '') + '</div>');
        
        if (!isSelf) {
            $item.click(function() {
                $(this).find('.red-dot').hide(); // Clear red dot on click
                openPrivateChat(u);
            });
        }
        $container.append($item);
    }

    function openPrivateChat(user) {
        currentPrivateUser = user;
        $('#pc-title').text('与 ' + user.username + ' 私聊');
        
        // Load message history
        $('#pc-messages').empty();
        if (privateHistory[user.id]) {
            privateHistory[user.id].forEach(function(msg) {
                appendMessage('#pc-messages', msg);
            });
        }
        
        $('#private-chat-modal').css('display', 'flex');
        $('#pc-input').focus();
    }

    function handlePrivateMessage(data) {
        var partnerId;
        // Logic: Who is the "Other" person in this conversation?
        if (data.sender_id === CURRENT_USER_ID) {
            // I sent it to recipient
            partnerId = data.recipient_id;
        } else {
            // I received it from sender
            partnerId = data.sender_id;
        }
        
        // Save to history
        if (!privateHistory[partnerId]) {
            privateHistory[partnerId] = [];
        }
        privateHistory[partnerId].push(data);

        // If the modal is open for this partner, show it.
        if (currentPrivateUser && currentPrivateUser.id === partnerId) {
            appendMessage('#pc-messages', data);
        } else {
            // If I received a message and window not open (or open for someone else)
            if (data.sender_id !== CURRENT_USER_ID) {
                // Show red dot instead of auto-opening
                // Find user item and show red dot
                var $userItem = $('.user-item[data-uid="' + partnerId + '"]');
                if ($userItem.length > 0) {
                    $userItem.find('.red-dot').show();
                }
            }
        }
    }

    function appendMessage(selector, data) {
        var $cont = $(selector);
        var isSelf = (data.sender_id === CURRENT_USER_ID);
        var rowClass = isSelf ? 'self' : 'other';
        
        var $row = $('<div class="message-row ' + rowClass + '"></div>');
        // Avatar
        var avatarChar = isSelf ? CURRENT_USERNAME.substring(0,1).toUpperCase() : data.sender.substring(0,1).toUpperCase();
        if (data.sender_id === 0) avatarChar = 'AI'; // AI Avatar
        
        $row.append('<div class="message-avatar">' + avatarChar + '</div>');
        
        var $content = $('<div class="message-content"></div>');
        var infoText = data.sender + ' ' + data.time;
        $content.append('<div class="message-info">' + escapeHtml(infoText) + '</div>');
        
        // Allow HTML for AI messages (sender_id === 0), escape others
        var msgHtml = (data.sender_id === 0) ? data.content : escapeHtml(data.content);
        $content.append('<div class="message-bubble">' + msgHtml + '</div>');
        
        $row.append($content);
        $cont.append($row);
        $cont.scrollTop($cont[0].scrollHeight);
    }

    function escapeHtml(text) {
        if (!text) return text;
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function dragElement(elmnt) {
        var pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
        var header = elmnt.querySelector('.pc-header');
        if (header) {
            header.onmousedown = dragMouseDown;
        } else {
            elmnt.onmousedown = dragMouseDown;
        }

        function dragMouseDown(e) {
            e = e || window.event;
            e.preventDefault();
            pos3 = e.clientX;
            pos4 = e.clientY;
            
            // Fix position before dragging if transform is present
            // This prevents jumping when removing the transform centering
            var style = window.getComputedStyle(elmnt);
            if (style.transform !== 'none') {
                var rect = elmnt.getBoundingClientRect();
                elmnt.style.top = rect.top + "px";
                elmnt.style.left = rect.left + "px";
                elmnt.style.transform = "none";
            }
            
            document.onmouseup = closeDragElement;
            document.onmousemove = elementDrag;
        }

        function elementDrag(e) {
            e = e || window.event;
            e.preventDefault();
            pos1 = pos3 - e.clientX;
            pos2 = pos4 - e.clientY;
            pos3 = e.clientX;
            pos4 = e.clientY;
            
            // Calculate new position
            elmnt.style.top = (elmnt.offsetTop - pos2) + "px";
            elmnt.style.left = (elmnt.offsetLeft - pos1) + "px";
            
            // Remove transform centering once dragged
            elmnt.style.transform = "none";
        }

        function closeDragElement() {
            document.onmouseup = null;
            document.onmousemove = null;
        }
    }
});
