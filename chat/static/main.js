
let ws;

function connect(event) {
    event.preventDefault(); // Prevent form submission

    const chatroom = document.getElementById("chatroom").value;
    if (ws) {
        ws.close(); // Close existing connection if present
    }
    ws = new WebSocket(`ws://127.0.0.1:{{port}}/chat/${chatroom}`);

    ws.addEventListener('message', function (event) {
        const li = document.createElement("li");
        li.appendChild(document.createTextNode(event.data));
        document.getElementById("messages").appendChild(li);
    });

    ws.addEventListener('open', function () {
        console.log(`Connected to chatroom: ${chatroom}`);
    });

    ws.addEventListener('close', function () {
        console.log(`Disconnected from chatroom: ${chatroom}`);
    });

    ws.addEventListener('error', function (error) {
        console.error('WebSocket error:', error);
    });
}

function send(event) {
    const message = (new FormData(event.target)).get("message");
    if (message && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(message);
    }
    event.target.reset(); // Reset the form after sending
    return false;
}


function overrideFormsWithClass(className) {
    // Select all forms with the given class
    const forms = document.querySelectorAll(`form.${className}`);

    forms.forEach(form => {
        form.addEventListener('submit', async (event) => {
            event.preventDefault(); // Prevent default form submission

            // Collect form data
            const formData = new FormData(form);
            const action = form.getAttribute('action');

            if (!action) {
                console.error('Form action URL is not specified.');
                return;
            }

            try {
                // Send POST request to the form's action URL
                const response = await fetch(action, {
                    method: 'POST',
                    body: formData
                });

                const responseData = await response.text();

                if (!response.ok) {
                    // Print an error if the response status is not OK
                    console.error('Error: Request failed with status', response.status);
                    console.error('Error details:', responseData);
                    return;
                }

                console.log('Response:', responseData);
                // Reload the page after successful submission
                window.location.reload();
            } catch (error) {
                console.error('Error submitting the form:', error);
            }
        });
    });
}

// Usage: Call this function and pass the target class name
overrideFormsWithClass('fetch-form');


