from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.http import HttpResponse
from django.urls import reverse
from .forms import InscriptionForm


def register_view(request):
    if request.method == 'POST':
        form = InscriptionForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Connecte automatiquement l'utilisateur après l'inscription
            login(request, user)
            if request.headers.get('HX-Request') == 'true':
                response = HttpResponse(status=204)
                response['HX-Redirect'] = reverse('login')
                return response
            return redirect('login')
    else:
        form = InscriptionForm()

    context = {'form': form}
    if request.headers.get('HX-Request') == 'true':
        return render(request, 'accounts/partials/register_form.html', context)
    return render(request, 'accounts/register.html', context)