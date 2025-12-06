frappe.listview_settings['Item'] = {
    onload(listview) {
        listview.page.add_inner_button(__('Upload Images (Excel)'), () => {
            new frappe.ui.FileUploader({
                doctype: 'Item',
                allow_multiple: false,
                restrictions: {
                    allowed_file_types: ['.xlsx']
                },
                on_success(file) {
                    frappe.call({
                        method: 'clevertech.design.server_scripts.item_image_import.upload_item_images_from_excel',
                        args: {
                            file_url: file.file_url
                        },
                        freeze: true,
                        callback(r) {
                            const msg = r.message;
                            let download_html = '';
                            console.log("Missing",msg.missing_file_url)
                            if (msg.missing_file_url) {
                                download_html = `
                                    <br><br>
                                   ️<a href="${msg.missing_file_url}"
                                         target="_blank"
                                         style="color:#1f6fd6; font-weight:600; text-decoration:underline;">
                                        Download missing item codes
                                    </a>
                                `;
                            }

                            frappe.msgprint({
                                title: __('Upload Summary'),
                                message: `
                                        Processed: ${msg.processed}<br>
                                        Missed: ${msg.missed}<br>
                                        Skipped: ${msg.skipped}<br>
                                        Failed: ${msg.failed}<br>
                                        ${download_html}<br>
                                    ${msg.logs.join('<br>')}
                                    
                                `,
                                indicator: msg.failed ? 'red' : 'green'
                            });
                        }
                    });
                }
            });
        });
    }
};

